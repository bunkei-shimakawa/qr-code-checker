import streamlit as st
import fitz  # PyMuPDF
from pyzbar.pyzbar import decode  # QRコード読み取り
from PIL import Image
import requests
import io
import pandas as pd
from bs4 import BeautifulSoup  # HTML解析用
from bokeh.plotting import figure
from bokeh.models import ColumnDataSource, HoverTool, Range1d, BoxSelectTool, TapTool
from bokeh.models.callbacks import CustomJS
from bokeh.models.widgets import DataTable, TableColumn
from bokeh.embed import file_html
from bokeh.resources import CDN

st.set_page_config(page_title="QRコード視覚化校正ツール", layout="wide")
st.title("📱 PDF紙面ベース QRコード校正ツール")
st.write("PDFをアップロードすると、紙面の上にQRコードの位置を赤枠で表示します。赤枠にマウスを重ねるとURLが、クリックすると詳細が表示されます。")

# ==========================================
# 補助関数（リダイレクト先の内容を取得）
# ==========================================
def get_url_details(url):
    """URLにアクセスし、最終URLとページ情報を取得する"""
    details = {
        "start_url": url,
        "final_url": "取得エラー",
        "title": "（取得できませんでした）",
        "description": "（取得できませんでした）",
        "og_image": None,
        "status": "アクセスエラー"
    }
    
    if not url.startswith("http"):
        details["final_url"] = "URL形式ではありません"
        details["status"] = "N/A"
        return details

    try:
        # allow_redirects=True で最終URLまで追跡
        response = requests.get(url, timeout=5, allow_redirects=True)
        details["final_url"] = response.url
        details["status"] = f"{response.status_code}"
        
        # HTMLの解析
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # タイトル、説明文、OGP画像の取得
        details["title"] = soup.title.string.strip() if soup.title else "（タイトルなし）"
        
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if not meta_desc: meta_desc = soup.find("meta", attrs={"property": "og:description"})
        details["description"] = meta_desc["content"].strip()[:100] + "..." if meta_desc else "（説明文なし）"
        
        meta_og_image = soup.find("meta", attrs={"property": "og:image"})
        details["og_image"] = meta_og_image["content"] if meta_og_image else None
        
    except requests.exceptions.RequestException as e:
        pass
        
    return details

# ==========================================
# メインの処理
# ==========================================
# PDFファイルのアップロード
uploaded_file = st.file_uploader("PDFファイルをアップロードしてください", type=["pdf"])

if uploaded_file is not None:
    results_list = []
    
    with st.spinner("PDFを解析中..."):
        # PDFを読み込む
        doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
        
        for page_num in range(len(doc)):
            st.subheader(f"📄 {page_num + 1} ページ目")
            
            page = doc.load_page(page_num)
            # QRコード認識用に高解像度画像を取得
            pix = page.get_pixmap(dpi=300)
            img = Image.open(io.BytesIO(pix.tobytes()))
            
            # 画像からQRコードをデコード
            decoded_objects = decode(img)
            
            if decoded_objects:
                # ==============================
                # QRコード情報を取得・整理
                # ==============================
                qr_coords = []
                for idx, obj in enumerate(decoded_objects):
                    qr_url = obj.data.decode('utf-8')
                    # QRの座標 (左上x, 左上y, 幅, 高さ)
                    x, y, w, h = obj.rect
                    
                    details = get_url_details(qr_url)
                    
                    # リスト用データに追加
                    results_list.append({
                        "ページ": page_num + 1,
                        "ID": f"{page_num + 1}-{idx + 1}",
                        "初期URL": details["start_url"],
                        "最終URL": details["final_url"],
                        "ページタイトル": details["title"],
                        "ステータス": details["status"]
                    })
                    
                    # 視覚化プロット用データに追加
                    qr_coords.append({
                        'x': x, 'y': y, 'w': w, 'h': h,
                        'id': f"{idx + 1}",
                        'url': qr_url,
                        'final_url': details["final_url"],
                        'title': details["title"],
                        'description': details["description"],
                        'og_image': details["og_image"]
                    })

                # ==============================
                # Bokehによる紙面の視覚化
                # ==============================
                st.write(f"{len(decoded_objects)} 個のQRコードが見つかりました。")
                
                # 画像のサイズに合わせてグラフの範囲を設定
                width, height = img.size
                
                # Bokeh Figureを作成（インタラクティブな機能を追加）
                # (Bokehはy軸が下から上に向かうので、画像を表示するために軸を反転させる)
                p = figure(x_range=Range1d(0, width), y_range=Range1d(height, 0),
                           width=900, height=int(900 * (height/width)),
                           tools=["pan,box_zoom,reset,tap,hover,save"],
                           tooltips=[("ID", "@id"), ("URL", "@url")],
                           title=f"紙面プレビュー（IDをホバー/タップ）")
                
                # 背景画像を描画
                p.image_rgba(image=[img], x=0, y=height, dw=width, dh=height)
                
                # QRコードの場所に赤い枠を描画
                source = ColumnDataSource(pd.DataFrame(qr_coords))
                rects = p.rect('x', 'y', 'w', 'h', source=source, 
                               fill_alpha=0.1, fill_color="red", line_color="red", line_width=2,
                               selection_fill_color="yellow", selection_line_color="yellow", selection_line_width=3)
                
                # Bokehのホバーツールの設定
                hover = p.select_one(HoverTool)
                hover.tooltips = [("ID", "@id"), ("URL", "@url")]
                
                # StreamlitにBokehのグラフを表示
                st.bokeh_chart(p, use_container_width=False)
                
                # ==============================
                # 選択されたQRコードの「リダイレクト先プレビュー」を表示
                # ==============================
                # ここでは単純に、このページで見つかったQRのリストとプレビューを表示する
                st.info("👇 上記の紙面で赤い枠をタップ、または以下のリストをクリックすると詳細が表示されます")
                
                # 各QRの詳細プレビュー
                for qr in qr_coords:
                    with st.expander(f"📌 ID: {qr['id']} - {qr['title']}", expanded=(len(qr_coords)==1)):
                        col_img, col_txt = st.columns([1, 2])
                        with col_img:
                            if qr['og_image']:
                                st.image(qr['og_image'], use_container_width=True)
                            else:
                                st.warning("OGP画像なし")
                        with col_txt:
                            st.markdown(f"**初期URL:** [{qr['url']}]({qr['url']})")
                            st.markdown(f"**最終URL (リダイレクト先):** [{qr['final_url']}]({qr['final_url']})")
                            st.markdown(f"**ページ概要:**\n\n> {qr['description']}")
                            
            else:
                st.write("このページにはQRコードが見つかりませんでした。")
                
    # ==========================================
    # 全体のまとめ（リスト化とCSV）
    # ==========================================
    if results_list:
        st.divider()
        st.subheader("📊 全体QRコードリスト")
        # データを表（データフレーム）にして表示
        df = pd.DataFrame(results_list)
        st.dataframe(df, use_container_width=True)
        
        # CSVダウンロードボタンの追加
        csv = df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="全リストをCSVとしてダウンロード",
            data=csv,
            file_name='qr_codes_校正リスト.csv',
            mime='text/csv',
        )