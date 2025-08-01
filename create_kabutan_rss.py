import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from datetime import datetime
import pytz
import re # 正規表現ライブラリは不要になったため削除してもOKですが、念のため残します

def generate_kabutan_rss():
    """
    株探の適時開示情報をスクレイピングし、RSSフィードを生成する関数
    """
    TARGET_URL = "https://kabutan.jp/disclosures/"
    HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    OUTPUT_FILE = "kabutan_tdnet.xml"
    DEBUG_FILE = "debug_page.html"

    try:
        response = requests.get(TARGET_URL, headers=HEADERS)
        response.raise_for_status()
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, 'lxml')

        # --- 変更点1: 表の探し方をより正確なものに修正 ---
        # "disclosure_box"クラスを持つdivの中の、"stock_table"クラスを持つtableを探す
        table = soup.select_one("div.disclosure_box > table.stock_table")

        if not table:
            print("エラー: 目的の開示情報テーブルが見つかりませんでした。")
            print(f"取得したHTMLをデバッグ用に '{DEBUG_FILE}' として保存します。")
            with open(DEBUG_FILE, "w", encoding="utf-8") as f:
                f.write(response.text)
            return

        # --- ここから下も、新しい表の構造に合わせて全面的に修正 ---

        fg = FeedGenerator()
        fg.title('株探 - 適時開示情報')
        fg.link(href=TARGET_URL, rel='alternate')
        fg.description('株探の適時開示情報ページから生成されたRSSフィードです。')
        fg.language('ja')
        jst = pytz.timezone('Asia/Tokyo')

        # ヘッダー行を除外するためにtbodyタグの中の行(tr)をすべて取得
        rows = table.find('tbody').find_all('tr')

        for row in rows:
            # 変更点2: tdとthタグの両方を取得し、6列あることを確認
            cells = row.find_all(['td', 'th'])
            if len(cells) == 6:
                # 変更点3: 新しい列構造に合わせて情報を取得
                code = cells[0].get_text(strip=True)
                company_name = cells[1].get_text(strip=True)
                # market = cells[2].get_text(strip=True) # 市場の情報は今回は使いませんが、取得は可能です
                # info_type = cells[3].get_text(strip=True) # 情報種別も同様
                title_tag = cells[4].find('a')
                time_str = cells[5].get_text(strip=True)

                if not title_tag:
                    continue
                
                title = title_tag.get_text(strip=True)
                # PDFアイコンのimgタグを除去してテキストを整形
                title = title.replace("pdf", "").strip()

                link = title_tag.get('href', '')
                # hrefが相対パスの場合、完全なURLに変換
                if link.startswith('/'):
                    link = "https://kabutan.jp" + link

                # 変更点4: 正規表現を使わずにタイトルを結合
                full_title = f"【{company_name} ({code})】{title}"

                now = datetime.now(jst)
                try:
                    # "25/08/01 13:41" のような形式をパース
                    pub_date = datetime.strptime(time_str, '%y/%m/%d %H:%M')
                    pub_date = jst.localize(pub_date) # タイムゾーン情報を付与
                except ValueError:
                    pub_date = now # 時間が取得できない場合は現在時刻を仮で設定

                fe = fg.add_entry()
                fe.title(full_title)
                fe.link(href=link)
                fe.description(f"適時開示：{title}")
                fe.pubDate(pub_date)
                fe.guid(link, permalink=True)

        fg.rss_file(OUTPUT_FILE, pretty=True)
        print(f"RSSフィード '{OUTPUT_FILE}' が正常に生成されました。")

    except requests.exceptions.RequestException as e:
        print(f"URLへのアクセス中にエラーが発生しました: {e}")
    except Exception as e:
        print(f"予期せぬエラーが発生しました: {e}")

if __name__ == "__main__":
    generate_kabutan_rss()