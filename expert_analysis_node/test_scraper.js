import { scrapeExpertAnalyses } from './src/scraper/index.js';

scrapeExpertAnalyses().then(res => {
  console.log('Total scraped:', res.length);
  res.forEach((r, i) => {
    console.log(`\n[${i+1}] Source: ${r.sourceName}`);
    console.log(`Text preview: ${r.rawText.substring(0, 300)}...`);
  });
}).catch(err => {
  console.error("Error:", err);
});
