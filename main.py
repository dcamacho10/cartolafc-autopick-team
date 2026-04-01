import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import time
import datetime
import json

from cartola_autopick.data_ingestion.api_client import CartolaAPIClient
from cartola_autopick.context_engine.profiler import Profiler
from cartola_autopick.optimizer.knapsack import TeamOptimizer
from cartola_autopick.optimizer.captain_bench import SecondaryOptimizer
from cartola_autopick.storage.db import (
    save_news_snippets, get_news_since, clear_old_news, get_news_log_stats
)

console = Console()


def summarize_team_momentum(analysis):
    """Build a short human-readable momentum summary from LLM scores."""
    if not isinstance(analysis, dict):
        return "Neutral"
    momentum = float(analysis.get("momentum_score", 1.0) or 1.0)
    risk = float(analysis.get("risk_score", 0.0) or 0.0)

    if momentum >= 1.2 and risk <= 0.3:
        return "Hot momentum"
    if momentum <= 0.8 and risk >= 0.6:
        return "Negative trend + high risk"
    if momentum <= 0.8:
        return "Negative trend"
    if risk >= 0.6:
        return "High rotation/injury risk"
    if momentum >= 1.2:
        return "Positive trend"
    if risk >= 0.4:
        return "Moderate risk"
    return "Neutral"


def build_llm_input_snippets(news_items):
    """Mirror MomentumLLM input trimming for transparent debugging."""
    items = []
    for n in (news_items[:6] if isinstance(news_items, list) else []):
        clean_n = str(n).replace('\n', ' ').strip()
        items.append(clean_n[:320] + "..." if len(clean_n) > 320 else clean_n)
    return items

@click.group()
def cli():
    """Cartola FC Autopick Team CLI"""
    pass


# ─────────────────────────────────────────────────────────────
# COLLECT COMMAND — meant to be run daily via cron / GitHub Actions
# ─────────────────────────────────────────────────────────────
@cli.command()
@click.option('--purge-days', default=7, help='Delete news older than N days (default 7)')
def collect(purge_days):
    """Scrape ESPN news for all teams and persist to the Supabase Cloud database."""
    console.print(Panel.fit(
        "[bold cyan]Cartola Autopick — Daily News Collector[/bold cyan]\n"
        f"[dim]{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}[/dim]"
    ))

    with console.status("[bold blue]Fetching club list from Cartola API...[/bold blue]"):
        api = CartolaAPIClient()
        market_data = api.get_market_players()
        clubs = market_data.get('clubes', {})

    with console.status("[bold blue]Discovering ESPN team IDs...[/bold blue]"):
        from cartola_autopick.data_ingestion.browser_scraper import discover_espn_ids, scrape_team_news_browser
        club_names = [c.get('nome', '') for c in clubs.values() if c.get('nome')]
        espn_ids = discover_espn_ids(club_names)
        console.print(f"  [green]✓[/green] Found IDs for {len(espn_ids)}/{len(club_names)} teams.")

    console.print("\n[bold yellow]Collecting news for each team...[/bold yellow]")
    stats_table = Table(show_header=True, header_style="dim")
    stats_table.add_column("Team")
    stats_table.add_column("Articles Found", justify="center")
    stats_table.add_column("Status", justify="center")

    total_saved = 0
    for club in clubs.values():
        team_name = club.get('nome', '')
        if not team_name:
            continue
        snippets = scrape_team_news_browser(team_name, espn_ids)
        if snippets:
            save_news_snippets(team_name, snippets)
            total_saved += len(snippets)
            status_str = "[green]✓ Saved[/green]"
        else:
            status_str = "[dim]No news[/dim]"
        stats_table.add_row(team_name, str(len(snippets)), status_str)

    console.print(stats_table)

    # Housekeeping: delete old news
    deleted = clear_old_news(older_than_days=purge_days)
    console.print(f"\n[dim]Housekeeping: removed {deleted} snippets older than {purge_days} days.[/dim]")
    console.print(f"[bold green]✓ Collection complete! {total_saved} new snippets saved.[/bold green]\n")


# ─────────────────────────────────────────────────────────────
# RUN COMMAND — reads accumulated news from DB, evaluates & picks team
# ─────────────────────────────────────────────────────────────
@cli.command()
@click.option('--strategy', type=click.Choice(['points', 'cartoletas']), default='points')
@click.option('--budget', type=float, default=100.0, help='Budget in cartoletas (C$)')
@click.option('--formation', type=str, default='4-3-3', help='Formation (e.g. 4-3-3, 3-4-3)')
@click.option('--days', type=int, default=7, help='Days of news history to use for AI analysis')
@click.option('--debug-ai', is_flag=True, help='Print deep per-team debug for AI news assembly and outputs')
def run(strategy, budget, formation, days, debug_ai):
    """Evaluate accumulated news and pick the optimal team for the round."""
    console.print(Panel.fit(
        f"[bold green]Cartola Autopick — Team Evaluator[/bold green]\n"
        f"Strategy: [cyan]{strategy}[/cyan] | Budget: [yellow]C${budget:.2f}[/yellow] | "
        f"Formation: [magenta]{formation}[/magenta] | News window: [blue]{days} days[/blue]"
    ))

    with console.status("[bold blue]1. Fetching Market Data from Cartola API...[/bold blue]"):
        api = CartolaAPIClient()
        status_data = api.get_market_status()
        if status_data.get('status_mercado') != 1:
            console.print("[bold red]Warning: The Cartola Market is currently CLOSED![/bold red]")
        market_data = api.get_market_players()
        matches_data = api.get_matches()
        players = market_data.get('atletas', [])
        clubs = market_data.get('clubes', {})
        posicoes = market_data.get('posicoes', {})
        partidas = matches_data.get('partidas', [])

    # ── Load news from DB ──────────────────────────────────────
    with console.status(f"[bold blue]2. Loading news from the current round window...[/bold blue]"):
        from cartola_autopick.storage.db import get_round_window_start
        window_start_ts = get_round_window_start()
        window_start_dt = datetime.datetime.fromtimestamp(window_start_ts)
        raw_news = get_news_since(days=days if days != 7 else None)  # None = auto round-window
        stats = get_news_log_stats()

    # Show DB + window status
    if stats['total_snippets'] == 0:
        console.print(
            f"[bold yellow]⚠ No news found in the Supabase DB for the current round window.[/bold yellow]\n"
            "  Run [cyan]python main.py collect[/cyan] first to gather news.\n"
        )
    else:
        oldest = datetime.datetime.fromtimestamp(stats['oldest']).strftime('%Y-%m-%d') if stats['oldest'] else 'N/A'
        newest = datetime.datetime.fromtimestamp(stats['newest']).strftime('%Y-%m-%d') if stats['newest'] else 'N/A'
        console.print(
            f"  [green]✓[/green] Round window starts: [cyan]{window_start_dt.strftime('%Y-%m-%d %H:%M')}[/cyan]  "
            f"| {stats['total_snippets']} articles, {stats['teams_covered']} teams "
            f"(collected {oldest} → {newest})"
        )


    # Map club_id → news snippets
    news_data = {}
    for club_id, club in clubs.items():
        team_name = club.get('nome', '')
        snippets = raw_news.get(team_name, [])
        news_data[club_id] = {'news': snippets}

    # ── AI Momentum Analysis ────────────────────────────────────
    with console.status("[bold blue]3. Analyzing Team Momentum (AI)...[/bold blue]"):
        from cartola_autopick.context_engine.momentum_llm import MomentumLLM
        llm = MomentumLLM()

        all_news_dict = {}
        for club_id, data in news_data.items():
            club_name = clubs.get(str(club_id), {}).get('nome', '')
            all_news_dict[club_name] = data['news']

        all_analysis = llm.analyze_all_teams(all_news_dict)

    if debug_ai:
        console.print("\n[bold cyan]AI Debug - Per Team Input/Output Audit:[/bold cyan]")
        for club_id, data in news_data.items():
            club_name = clubs.get(str(club_id), {}).get('nome', '')
            raw_snippets = data.get('news', [])
            llm_input_snippets = build_llm_input_snippets(raw_snippets)
            analysis = all_analysis.get(club_name, {})
            if not isinstance(analysis, dict):
                analysis = {}
            analysis_view = {
                "momentum_score": analysis.get("momentum_score", 1.0),
                "risk_score": analysis.get("risk_score", 0.0),
                "summary": summarize_team_momentum(analysis),
                "reasoning": analysis.get("reasoning", "No news available."),
            }
            debug_payload = {
                "team": club_name,
                "club_id": club_id,
                "raw_news_count_db": len(raw_snippets),
                "llm_input_count": len(llm_input_snippets),
                "llm_input_snippets": llm_input_snippets,
                "llm_output": analysis_view,
            }
            console.print(
                Panel(
                    json.dumps(debug_payload, ensure_ascii=False, indent=2),
                    title=f"Debug - {club_name}",
                    border_style="cyan",
                )
            )

    console.print("\n[bold yellow]AI Team Momentum Summary:[/bold yellow]")
    momentum_table = Table(show_header=True, header_style="dim")
    momentum_table.add_column("Team")
    momentum_table.add_column("Mom.", justify="center")
    momentum_table.add_column("Risk", justify="center")
    momentum_table.add_column("Articles", justify="center")
    momentum_table.add_column("Summary")
    momentum_table.add_column("AI Reasoning")

    for club_id, data in news_data.items():
        club_name = clubs.get(str(club_id), {}).get('nome', '')
        analysis = all_analysis.get(club_name, {})
        if not isinstance(analysis, dict): analysis = {}
        if 'momentum_score' not in analysis: analysis['momentum_score'] = 1.0
        if 'risk_score' not in analysis: analysis['risk_score'] = 0.0
        if 'reasoning' not in analysis: analysis['reasoning'] = "No news available."
        data['llm'] = analysis

        momentum_table.add_row(
            club_name,
            f"{analysis['momentum_score']:.1f}",
            f"{analysis['risk_score']:.1f}",
            str(len(data['news'])),
            summarize_team_momentum(analysis),
            analysis['reasoning']
        )

    console.print(momentum_table)

    # ── Profiler + Optimizer ────────────────────────────────────
    with console.status("[bold blue]4. Generating Player Profiles...[/bold blue]"):
        profiler = Profiler()
        profiles = profiler.generate_profiles(players, clubs, partidas, news_data)

    with console.status("[bold blue]5. Running PuLP Optimizer...[/bold blue]"):
        optimizer = TeamOptimizer(budget=budget, strategy=strategy, formation=formation)
        selected_team = optimizer.optimize(profiles)
        sec_opt = SecondaryOptimizer()
        selected_team = sec_opt.select_captain(selected_team)
        spent = sum(p['price'] for p in selected_team)
        remaining = budget - spent
        bench = sec_opt.select_bench(profiles, selected_team, remaining, formation)

    # ── Match Analysis Display ──────────────────────────────────
    from cartola_autopick.context_engine.match_analyzer import MatchAnalyzer
    analyzer = MatchAnalyzer()
    console.print("\n[bold yellow]Round Matches & Team Strengths:[/bold yellow]")
    matches_table = Table(show_header=True, header_style="dim")
    matches_table.add_column("Home Team")
    matches_table.add_column("Str", justify="center")
    matches_table.add_column("vs", justify="center")
    matches_table.add_column("Away Team")
    matches_table.add_column("Str", justify="center")
    matches_table.add_column("Home Momentum")
    matches_table.add_column("Away Momentum")
    matches_table.add_column("Analysis", justify="center")

    for m in partidas:
        home_id = m.get('clube_casa_id')
        away_id = m.get('clube_visitante_id')
        home_name = clubs.get(str(home_id), {}).get('nome', 'Unknown')
        away_name = clubs.get(str(away_id), {}).get('nome', 'Unknown')
        home_momentum = summarize_team_momentum(all_analysis.get(home_name, {}))
        away_momentum = summarize_team_momentum(all_analysis.get(away_name, {}))
        analysis = analyzer.analyze_match(m)
        cls_text = analysis['classification']
        if cls_text == "home_favorite":
            cls_styled = f"[green]{home_name}[/green]"
        elif cls_text == "away_favorite":
            cls_styled = f"[green]{away_name}[/green]"
        else:
            cls_styled = "[yellow]Equilibrium[/yellow]"
        matches_table.add_row(
            home_name, str(analysis['home_score']), "X",
            away_name, str(analysis['away_score']),
            home_momentum, away_momentum, cls_styled
        )
    console.print(matches_table)

    # ── Final Team Display ──────────────────────────────────────
    console.print("\n[bold green]Optimization Complete! Here is your team:[/bold green]")
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Pos")
    table.add_column("Player Name")
    table.add_column("Club")
    table.add_column("Price (C$)", justify="right")
    table.add_column("Exp. Pts", justify="right")
    table.add_column("Captain?", justify="center")

    selected_team.sort(key=lambda x: x['position_id'])
    total_expected = 0.0
    for p in selected_team:
        pos_name = posicoes.get(str(p['position_id']), {}).get('abreviacao', '')
        club_name = clubs.get(str(p['club_id']), {}).get('nome', '')
        is_cap = "[bold yellow]C[/bold yellow]" if p.get('is_captain') else ""
        pts = p['expected_points']
        if p.get('is_captain'):
            pts *= 2
        total_expected += pts
        table.add_row(pos_name, p['name'], club_name, f"C${p['price']:.2f}", f"{pts:.2f}", is_cap)

    console.print(table)
    console.print(f"\n[bold]Total Spent:[/bold] C${spent:.2f} (Remaining: C${remaining:.2f})")
    console.print(f"[bold]Total Expected Points:[/bold] {total_expected:.2f}\n")

    if bench:
        console.print("[bold yellow]Substitutes (Bench):[/bold yellow]")
        bench_table = Table(show_header=True, header_style="dim")
        bench_table.add_column("Pos")
        bench_table.add_column("Player Name")
        bench_table.add_column("Price (C$)", justify="right")
        bench.sort(key=lambda x: x['position_id'])
        for b in bench:
            pos_name = posicoes.get(str(b['position_id']), {}).get('abreviacao', '')
            bench_table.add_row(pos_name, b['name'], f"C${b['price']:.2f}")
        console.print(bench_table)


if __name__ == '__main__':
    cli()
