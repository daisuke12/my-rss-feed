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

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}

def load_processed_links():
    """確認済みのリンクをファイルから読み込む"""
    if not os.path.exists(STATE_DB_FILE):
        return set()
    with open(STATE_DB_FILE, 'r', encoding='utf-8') as f:
        return set(json.load(f))

def save_processed_links(links_set):
    """確認済みのリンクをファイルに保存する"""
    with open(STATE_DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(links_set), f, indent=2)

def generate_full_disclosure_rss():
    """
    株探の複数ページを巡回し、未処理の開示情報のみを扱うRSSフィードを生成する
    """
    print("処理を開始します...")
    
    # 1. 過去に処理したリンクを読み込む
    processed_links = load_processed_links()
    print(f"確認済みのリンクを {len(processed_links)} 件読み込みました。")
    
    all_items = []
    new_item_found_flag = False

    # 2. 指定したページ数だけ株探を巡回
    for page in range(1, MAX_PAGES_TO_SCRAPE + 1):
        # 2ページ目以降はURLにパラメータを追加
        url = TARGET_URL_BASE if page == 1 else f"{TARGET_URL_BASE}?page={page}"
        print(f"{page} ページ目を巡回中: {url}")
        
        try:
            response = requests.get(url, headers=HEADERS)
            response.raise_for_status()
            response.encoding = response.apparent_encoding
            soup = BeautifulSoup(response.text, 'lxml')

            table = soup.select_one("div.disclosure_box > table.stock_table")
            if not table:
                print(f"{page} ページ目でテーブルが見つかりませんでした。次のページへ進みます。")
                continue

            rows = table.find('tbody').find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) != 6:
                    continue

                title_tag = cells[4].find('a')
                if not title_tag:
                    continue
                    
                # まず、判定に使うためのタイトルテキストを取得します
                title_text_for_check = title_tag.get_text(strip=True)

                # 除外したいキーワードのリストを定義します
                exclude_keywords = ["定時株主総会","提案書","Report", "Results", "Summary", "Notice", "Presentation", "Announcement", "自己株式", "ガバナンス", "Share", "Notification", "Status", "訂正", "払込", "経過", "Status", "人事異動", "results", "行使状況", "Regarding", "of", "for", "the", "ETF", "招集ご通知", "株主総会資料", "REIT", "独立役員届出書", "発行内容確定", "定款", "ＥＴＦ", "ＥＴＮ", "ETN", "日々の開示", "認証取得"]
                
                # タイトルに除外キーワードのいずれかが含まれているかチェックします
                if any(keyword in title_text_for_check for keyword in exclude_keywords):
                    continue # 含まれていたら、この開示情報の処理をスキップして次の行に進みます
                    
                link = title_tag.get('href', '')
                if link.startswith('/'):
                    link = "https://kabutan.jp" + link
                
                # このリンクが未処理の場合のみ情報を組み立てる
                if link not in processed_links:
                    new_item_found_flag = True
                
                # all_itemsには全件（新旧問わず）追加する
                item_data = {
                    "code": cells[0].get_text(strip=True),
                    "company_name": cells[1].get_text(strip=True),
                    "title": title_tag.get_text(strip=True).replace("pdf", "").strip(),
                    "time_str": cells[5].get_text(strip=True),
                    "link": link
                }
                all_items.append(item_data)
                
        except requests.exceptions.RequestException as e:
            print(f"{page} ページ目の取得に失敗しました: {e}")
            continue # エラーが起きても次のページの処理を試みる
        
        # サーバーに負荷をかけすぎないための小休止
        time.sleep(1) 

    # 3. 新しいアイテムが見つからなかった場合は、処理を終了
    # --- 以下をコメントアウト ---
# if not new_item_found_flag:
#     print("新しい開示情報はありませんでした。処理を終了します。")
#     return

    print("新しい開示情報を検出しました。RSSフィードを生成します。")
    
    # 4. RSSフィードを生成
    fg = FeedGenerator()
    fg.title('株探 - 適時開示情報 (全件監視用)')
    fg.link(href=TARGET_URL_BASE, rel='alternate')
    fg.description('株探の適時開示情報を複数ページ巡回して生成されたRSSフィードです。')
    fg.language('ja')
    jst = pytz.timezone('Asia/Tokyo')
    
    # RSSフィードには最新N件のみを掲載（Feedlyの負荷軽減のため）
    for item in all_items[:MAX_ITEMS_IN_RSS]:
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
        fe.guid(item['link'], permalink=True) # GUID（ユニークID）が最も重要

    # 5. 生成したRSSファイルと、更新された確認済みリストを保存
    fg.rss_file(OUTPUT_RSS_FILE, pretty=True)
    
    # 新しく見つかったアイテムのリンクを全て確認済みリストに追加
    updated_links = processed_links.union(item['link'] for item in all_items)
    save_processed_links(updated_links)
    
    print(f"RSSフィード '{OUTPUT_RSS_FILE}' が正常に更新されました。")
    print(f"確認済みリンクを {len(updated_links)} 件に更新しました。")

if __name__ == "__main__":
    generate_full_disclosure_rss()
