import json
import time
from bs4 import BeautifulSoup
import pandas as pd
from playwright.sync_api import sync_playwright


def scrape_kijiji_rentals(search_url: str, max_pages: int = 1) -> list[dict]:
    listings = []

    with sync_playwright() as p:
        # Launch browser with standard desktop user-agent
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
        )
        page = context.new_page()

        for current_page in range(1, max_pages + 1):
            target_url = (
                search_url
                if current_page == 1
                else f"{search_url}/page-{current_page}"
            )
            print(f"Fetching page {current_page}: {target_url}")

            page.goto(target_url, wait_until="domcontentloaded", timeout=60000)

            # Allow DOM hydration and dynamic scripts to settle
            page.wait_for_timeout(3000)

            html = page.content()
            soup = BeautifulSoup(html, "html.parser")

            found_on_page = 0

            # Method A: Parse structured Schema.org JSON-LD (most resilient)
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict) and data.get("@type") == "ItemList":
                        items = data.get("itemListElement", [])
                        for el in items:
                            item = el.get("item", {})
                            name = item.get("name")
                            url = item.get("url")
                            offers = item.get("offers", {})
                            price = (
                                offers.get("price")
                                if isinstance(offers, dict)
                                else None
                            )
                            description = item.get("description")

                            if name and url:
                                listings.append(
                                    {
                                        "title": name,
                                        "price": price,
                                        "url": url,
                                        "description": description,
                                        "page": current_page,
                                    }
                                )
                                found_on_page += 1
                except (json.JSONDecodeError, TypeError):
                    continue

            # Method B: Fallback to HTML listing cards if JSON-LD wasn't populated
            if found_on_page == 0:
                cards = soup.select('[data-testid="listing-card"], article')
                for card in cards:
                    title_el = card.select_one(
                        '[data-testid="listing-title"], h3, a[data-testid="listing-link"]'
                    )
                    price_el = card.select_one('[data-testid="listing-price"]')
                    link_el = card.select_one('a[href*="/v-"]')

                    if title_el and link_el:
                        raw_href = link_el.get("href", "")
                        full_url = (
                            f"https://www.kijiji.ca{raw_href}"
                            if raw_href.startswith("/")
                            else raw_href
                        )
                        listings.append(
                            {
                                "title": title_el.get_text(strip=True),
                                "price": (
                                    price_el.get_text(strip=True)
                                    if price_el
                                    else None
                                ),
                                "url": full_url,
                                "description": None,
                                "page": current_page,
                            }
                        )
                        found_on_page += 1

            print(
                f"Extracted {found_on_page} listings from page {current_page}."
            )

            # Politeness delay between pages
            time.sleep(2)

        browser.close()

    return listings


if __name__ == "__main__":
    # Example: Apartments & Condos for rent in Toronto
    # (Replace with your specific regional rental search URL)
    rental_search_url = (
        "https://www.kijiji.ca/b-apartments-condos/kawartha-lakes/c37l1700219?view=list"
    )

    df = scrape_kijiji_rentals(rental_search_url, max_pages=2)

    if df:
        output_file = "kijiji_rentals.csv"
        df.to_csv(output_file, index=False)
        print(
            f"\nSaved {len(df)} unique listings to {output_file}."
        )
        print(df[["title", "price", "url"]].head())
    else:
        print("No listings found.")