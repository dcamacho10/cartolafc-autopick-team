import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from cartola_autopick.data_ingestion.api_client import CartolaAPIClient
from cartola_autopick.data_ingestion.scraper import NewsScraper
from cartola_autopick.context_engine.profiler import Profiler
from cartola_autopick.optimizer.knapsack import TeamOptimizer
from cartola_autopick.optimizer.captain_bench import SecondaryOptimizer

console = Console()

@click.group()
def cli():
    """Cartola FC Autopick Team CLI"""
    pass

@cli.command()
@click.option('--strategy', type=click.Choice(['points', 'cartoletas']), default='points', help='Optimization strategy')
@click.option('--budget', type=float, default=100.0, help='Available team budget in cartoletas (C$)')
@click.option('--formation', type=str, default='4-3-3', help='Tactical formation (e.g., 4-3-3, 3-4-3, 4-4-2, 3-5-2)')
def run(strategy, budget, formation):
    """Run the auto-picker with the specified parameters."""
    console.print(Panel.fit(f"[bold green]Cartola Autopick Master[/bold green]\nStrategy: [cyan]{strategy}[/cyan] | Budget: [yellow]C${budget:.2f}[/yellow] | Formation: [magenta]{formation}[/magenta]"))
    
    with console.status("[bold blue]1. Fetching Market Data from Cartola API...[/bold blue]"):
        api = CartolaAPIClient()
        status_data = api.get_market_status()
        
        if status_data.get('status_mercado') != 1:
            console.print("[bold red]Warning: The Cartola Market is currently CLOSED![/bold red]")
            # We continue for testing purposes, but normally we'd warn the user
            
        market_data = api.get_market_players()
        matches_data = api.get_matches()
        
        players = market_data.get('atletas', [])
        clubs = market_data.get('clubes', {})
        posicoes = market_data.get('posicoes', {})
        partidas = matches_data.get('partidas', [])
        
    with console.status("[bold blue]2. Scraping Recent News for Context Engine...[/bold blue]"):
        scraper = NewsScraper()
        news_data = {}
        # Fetching news for a few clubs as an example to avoid hitting rate limits on test
        # In a real run, we'd fetch for all 20 clubs.
        for club_id, club in clubs.items():
             news_data[club_id] = scraper.get_team_news(club.get('nome', ''))
             
    with console.status("[bold blue]3. Generating Player Profiles (Applying Rules, Match Analysis & LLM)...[/bold blue]"):
        profiler = Profiler()
        profiles = profiler.generate_profiles(players, clubs, partidas, news_data)
        
    with console.status("[bold blue]4. Running PuLP Optimizer...[/bold blue]"):
        optimizer = TeamOptimizer(budget=budget, strategy=strategy, formation=formation)
        selected_team = optimizer.optimize(profiles)
        
        sec_opt = SecondaryOptimizer()
        selected_team = sec_opt.select_captain(selected_team)
        
        spent = sum(p['price'] for p in selected_team)
        remaining = budget - spent
        bench = sec_opt.select_bench(profiles, selected_team, remaining, formation)
        
    # Display Output
    console.print("\n[bold green]Optimization Complete! Here is your team:[/bold green]")
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Pos")
    table.add_column("Player Name")
    table.add_column("Club")
    table.add_column("Price (C$)", justify="right")
    table.add_column("Exp. Pts", justify="right")
    table.add_column("Captain?", justify="center")
    
    # Sort team by position id
    selected_team.sort(key=lambda x: x['position_id'])
    
    total_expected = 0.0
    for p in selected_team:
        pos_name = posicoes.get(str(p['position_id']), {}).get('abreviacao', '')
        club_name = clubs.get(str(p['club_id']), {}).get('nome', '')
        is_cap = "[bold yellow]C[/bold yellow]" if p.get('is_captain') else ""
        pts = p['expected_points']
        if p.get('is_captain'):
            pts *= 2 # Cartola rules: Captain points are doubled
        total_expected += pts
        
        table.add_row(
            pos_name, 
            p['name'], 
            club_name, 
            f"C${p['price']:.2f}", 
            f"{pts:.2f}",
            is_cap
        )
        
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
