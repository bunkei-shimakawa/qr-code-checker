import streamlit as st
import fitz  # PyMuPDF
from pyzbar.pyzbar import decode  # QRコード読み取り
from PIL import Image, ImageDraw
import requests
import io
import pandas as pd
from bs4 import BeautifulSoup  # HTML解析用

st.set_page_config(page_title="QRコード視覚化校正ツール", layout="wide")
st.title("📱 PDF紙面ベース QRコード校正ツール")
st.write("PDFをアップロードすると、紙面上にQRコードの位置を赤枠で示し、下部にリンク先やプレビューを表示します。")

# ==========================================
# 補助関数（リダイレクト先の内容を取得）
# ==========================================
def get_url_details(url):
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
        response = requests.get(url, timeout=5, allow_redirects=True)
        details["final_url"] = response.url
        details["status"] = f"{response.status_code}"
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        details["title"] = soup.title.string.strip() if soup.title else "（タイトルなし）"
        
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if not meta_desc: meta_desc = soup.find("meta", attrs={"property": "og:description"})
        details["description"] = meta_desc["content"].strip()[:100] + "..." if meta_desc and meta_desc.get("content") else "（説明文なし）"
        
        meta_og_image = soup.find("meta", attrs={"property": "og:image"})
        details["og_image"] = meta_og_image["content"] if meta_og_image and meta_og_image.get("content") else None
        
    except Exception as e:
        pass
        
    return details

# ==========================================
# メインの処理
# ==========================================
uploaded_file = st.file_uploader("PDFファイルをアップロードしてください", type=["pdf"])

if uploaded_file is not None:
    results_list = []
    
    with st.spinner("PDFを解析中..."):
        doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
        
        for page_num in range(len(doc)):
            st.markdown(f"### 📄 {page_num + 1} ページ目")
            
            page = doc.load_page(page_num)
            pix = page.get_pixmap(dpi=200) # メモリ負荷軽減のため少し解像度を調整
            # 画像として読み込み、描画用に変換
            img = Image.open(io.BytesIO(pix.tobytes())).convert("RGB")
            draw = ImageDraw.Draw(img)
            
            decoded_objects = decode(img)
            
            if decoded_objects:
                qr_details = []
                
                # 画像に直接赤枠を描き込む
                for idx, obj in enumerate(decoded_objects):
                    qr_url = obj.data.decode('utf-8')
                    # QRの座標 (左上x, 左上y, 幅, 高さ)
                    # Polygon（ポリゴン）情報を使って正確な四角形を描画
                    pts = obj.polygon
                    if len(pts) == 4:
                        draw.polygon([(pts[0].x, pts[0].y), (pts[1].x, pts[1].y), 
                                      (pts[2].x, pts[2].y), (pts[3].x, pts[3].y)], 
                                     outline="red", width=8)
                    else:
                        x, y, w, h = obj.rect
                        draw.rectangle([x, y, x+w, y+h], outline="red", width=8)
                        
                    # 近くに番号（ID）を描画（少し大きめの赤い四角を背景に）
                    text_x, text_y = obj.rect.left, max(0, obj.rect.top - 40)
                    draw.rectangle([text_x, text_y, text_x + 40, text_y + 40], fill="red")
                    
                    # URL情報を取得
                    details = get_url_details(qr_url)
                    details["id"] = idx + 1
                    qr_details.append(details)
                    
                    # リスト用データに追加
                    results_list.append({
                        "ページ": page_num + 1,
                        "ID": f"{page_num + 1}-{idx + 1}",
                        "初期URL": details["start_url"],
                        "最終URL": details["final_url"],
                        "ページタイトル": details["title"],
                        "ステータス": details["status"]
                    })

                # Streamlitで画像（赤枠付き）を表示
                st.image(img, use_container_width=True, caption=f"{page_num + 1}ページ目のプレビュー")
                
                # ==============================
                # 検出されたQRコードの詳細プレビューを表示
                # ==============================
                st.info("👇 検出されたQRコードの詳細（画像内の赤枠に対応しています）")
                for qr in qr_details:
                    with st.expander(f"📌 ID: {qr['id']} - {qr['title']}", expanded=True):
                        col_img, col_txt = st.columns([1, 2])
                        with col_img:
                            if qr['og_image']:
                                st.image(qr['og_image'], use_container_width=True)
                            else:
                                st.warning("OGP画像なし")
                        with col_txt:
                            st.markdown(f"**初期URL:** [{qr['start_url']}]({qr['start_url']})")
                            st.markdown(f"**最終URL (リダイレクト先):** [{qr['final_url']}]({qr['final_url']})")
                            st.markdown(f"**ページ概要:**\n> {qr['description']}")
                            
            else:
                st.image(img, use_container_width=True)
                st.warning("このページにはQRコードが見つかりませんでした。")
                
        st.divider()

    # ==========================================
    # 全体のまとめ（リスト化とCSV）
    # ==========================================
    if results_list:
        st.subheader("📊 全体QRコードリスト")
        df = pd.DataFrame(results_list)
        st.dataframe(df, use_container_width=True)
        
        csv = df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="全リストをCSVとしてダウンロード",
            data=csv,
            file_name='qr_codes_校正リスト.csv',
            mime='text/csv',
        )