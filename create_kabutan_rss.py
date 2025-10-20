import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from datetime import datetime
import pytz
import json
import os
import time

# --- 設定項目 ---
# 巡回する最大のページ数（決算期は多めに設定）
MAX_PAGES_TO_SCRAPE = 100
# RSSフィードに含める最大アイテム数
MAX_ITEMS_IN_RSS = 2000
# --- 設定項目ここまで ---

# --- ファイル名定義 ---
TARGET_URL_BASE = "https://kabutan.jp/disclosures/"
OUTPUT_RSS_FILE = "kabutan_tdnet.xml"
STATE_DB_FILE = "processed_links.json" # 確認済みリンクを保存するファイル
# --- ファイル名定義ここまで ---

# --- 除外キーワードリスト ---
# ループの外に定義することで、毎回リストを生成する無駄をなくします
EXCLUDE_KEYWORDS = [
    "定時株主総会","提案書","Report", "Results", "Summary", "Notice", "Presentation", "Announcement", "自己株式", "ガバナンス",
    "Share", "Notification", "Status", "訂正", "払込", "経過", "人事異動", "results", "行使状況", "Regarding", "of", "for",
    "the", "ETF", "招集ご通知", "株主総会資料", "REIT", "独立役員届出書", "発行内容確定", "定款", "ＥＴＦ", "ＥＴＮ", "ETN",
    "日々の開示", "認証取得", "統合レポート", "統合報告書", "1308","1348","1473","2557","1305","1475","2625","1306","2524","1330","1346","1578","1369",
    "1397","1320","1321","1329","2525","2624","1592","1593","1474","1591","1364","2526","1319","2516","1563","1551","2017",
    "159A","348A","1311","1493","1617","1618","1619","1620","1621","1622","1623","1624","1625","1626","1627","1628","1629",
    "1630","1631","1632","1633","1615","1698","1577","1586","2523","1585","1596","1477","1478","1399","1479","1480","1481",
    "1484","1483","1485","399A","1489","1494","1651","1652","2518","1653","1654","1498","2529","2560","2642","2567","2564",
    "2626","2627","2636","2637","2638","2639","2640","2641","2643","2644","2645","2646","2836","2837","2847","2848","2849",
    "2851","2854","2250","213A","221A","200A","234A","235A","282A","294A","315A","328A","354A","1490","1499","2858","2865",
    "2868","379A","2863","1345","1597","1398","2552","2555","2556","1343","1476","1488","1595","2517","360A","2528","2527",
    "2565","1555","1495","1659","1660","2515","2566","2852","2855","2864","2096","2097","2098","2018","210A","1322","2553",
    "1309","2530","2628","2629","1678","201A","233A","188A","1559","1560","1679","1546","2562","2846","2235","2241","2242",
    "2088","1547","1557","2558","2633","1655","2521","2563","2630","2634","2247","2248","2086","2635","2236","2095","364A",
    "318A","313A","346A","356A","383A","426A","1545","2568","2569","2631","2632","2840","2841","2845","2087","392A","1325",
    "1680","1550","2513","2514","1681","2520","1554","2559","1657","1658","2522","2859","2860","2089","2867","2243","2244",
    "2252","2253","2254","2013","2014","178A","223A","224A","273A","283A","295A","316A","363A","380A","404A","412A","413A",
    "2510","2561","236A","1349","1677","2511","2512","1566","2519","1482","1486","1487","1496","1497","1656","2554","2620",
    "2621","2622","2623","2647","2648","376A","2090","2838","2839","2649","2856","2255","2256","2257","2258","2012","133A",
    "179A","180A","181A","182A","183A","237A","238A","2843","2844","2853","2857","2245","2091","2861","2862","2246","2092",
    "2259","2866","2019","1328","1326","1672","1540","314A","424A","425A","1674","1541","1673","1542","1675","1543","1671",
    "1699","1676","1684","1685","1686","1687","1688","1689","1690","1691","1692","1693","1694","1695","1696","1697","1599",
    "2080","2081","2082","2083","2084","2085","2093","2011","2015","2016","170A","257A","258A","349A","381A","382A","394A",
    "395A","396A","408A", "8951","8952","8953","8954","8955","8956","8957","8958","8960","8961","8964","8966","8967","8968",
    "8972","8975","8976","8977","8984","8985","8986","8987","8963","3226","3234","3249","3269","8979","3279","3281","3282",
    "3283","3287","3290","3292","3295","3296","3451","3309","3455","3459","3462","3463","3466","3468","3470","3471","3472",
    "3476","3481","3487","3488","3492","2971","2972","2979","2989","401A"
]
# --- 除外キーワードリストここまで ---


HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

def load_processed_links():
    """確認済みのリンクをファイルから読み込む"""
    if not os.path.exists(STATE_DB_FILE):
        return set()
    try:
        with open(STATE_DB_FILE, 'r', encoding='utf-8') as f:
            return set(json.load(f))
    except (json.JSONDecodeError, IOError):
        return set() # ファイルが空または壊れている場合は空のセットを返す

def save_processed_links(links_set):
    """確認済みのリンクをファイルに保存する"""
    with open(STATE_DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(links_set), f, indent=2, ensure_ascii=False)

def generate_full_disclosure_rss():
    """
    株探の複数ページを巡回し、未処理の開示情報のみを扱うRSSフィードを生成する
    """
    print("処理を開始します...")
    
    processed_links = load_processed_links()
    print(f"確認済みのリンクを {len(processed_links)} 件読み込みました。")
    
    all_items = []

    for page in range(1, MAX_PAGES_TO_SCRAPE + 1):
        url = TARGET_URL_BASE if page == 1 else f"{TARGET_URL_BASE}?page={page}"
        print(f"{page} ページ目を巡回中: {url}")
        
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            response.raise_for_status()
            response.encoding = response.apparent_encoding
            soup = BeautifulSoup(response.text, 'lxml')

            table = soup.select_one("div.disclosure_box > table.stock_table")
            if not table:
                print(f"{page} ページ目でテーブルが見つかりませんでした。処理を中断します。")
                break

            rows = table.find('tbody').find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) != 6:
                    continue

                title_tag = cells[4].find('a')
                if not title_tag:
                    continue
                
                # --- ★★★ 修正箇所 ★★★ ---
                # 判定に使うための「銘柄コード」と「タイトル」を取得
                code_text = cells[0].get_text(strip=True)
                title_text = title_tag.get_text(strip=True)

                # 「タイトル」または「銘柄コード」に除外キーワードが含まれているかチェック
                if any(keyword in title_text for keyword in EXCLUDE_KEYWORDS) or \
                   code_text in EXCLUDE_KEYWORDS:
                    continue # 含まれていたら、この情報の処理をスキップ
                # --- ★★★ 修正ここまで ★★★ ---
                
                link = title_tag.get('href', '')
                if link.startswith('/'):
                    link = "https://kabutan.jp" + link
                
                # all_itemsにはフィルター後の全件を追加する
                item_data = {
                    "code": code_text,
                    "company_name": cells[1].get_text(strip=True),
                    "title": title_text.replace("pdf", "").strip(),
                    "time_str": cells[5].get_text(strip=True),
                    "link": link
                }
                all_items.append(item_data)
                
        except requests.exceptions.RequestException as e:
            print(f"{page} ページ目の取得に失敗しました: {e}")
            continue
        
        time.sleep(1)

    if not all_items:
        print("処理対象の開示情報はありませんでした。処理を終了します。")
        return

    print(f"フィルター後の開示情報を {len(all_items)} 件取得しました。RSSフィードを生成します。")
    
    # RSSフィードを生成
    fg = FeedGenerator()
    fg.title('株探 - 適時開示情報')
    fg.link(href=TARGET_URL_BASE, rel='alternate')
    fg.description('株探の適時開示情報から特定キーワードを除外したRSSフィードです。')
    fg.language('ja')
    jst = pytz.timezone('Asia/Tokyo')
    
    # 新しいアイテムのみをprocessed_linksに追加するためのセット
    new_links_to_add = set()

    for item in all_items[:MAX_ITEMS_IN_RSS]:
        # このリンクが未処理の場合のみ、new_links_to_add に追加
        if item['link'] not in processed_links:
            new_links_to_add.add(item['link'])

        full_title = f"【{item['company_name']} ({item['code']})】{item['title']}"
        
        try:
            pub_date = datetime.strptime(item['time_str'], '%y/%m/%d %H:%M')
            pub_date = jst.localize(pub_date)
        except ValueError:
            pub_date = datetime.now(jst)

        fe = fg.add_entry()
        fe.title(full_title)
        fe.link(href=item['link'])
        fe.description(f"適時開示：{item['title']}")
        fe.pubDate(pub_date)
        fe.guid(item['link'], permalink=True)

    fg.rss_file(OUTPUT_RSS_FILE, pretty=True)
    
    # 確認済みリストを更新
    updated_links = processed_links.union(new_links_to_add)
    save_processed_links(updated_links)
    
    print(f"RSSフィード '{OUTPUT_RSS_FILE}' が正常に更新されました。")
    print(f"{len(new_links_to_add)} 件の新しい情報が追加されました。")
    print(f"確認済みリンクを {len(updated_links)} 件に更新しました。")

if __name__ == "__main__":
    generate_full_disclosure_rss()
