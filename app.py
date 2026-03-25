import streamlit as st
import fitz  # PyMuPDF: PDFを画像化するライブラリ
from pyzbar.pyzbar import decode  # QRコード読み取りライブラリ
from PIL import Image
import requests
import io
import pandas as pd

st.set_page_config(page_title="QRコード校正ツール", layout="wide")
st.title("📱 PDF内 QRコード検出＆リダイレクト確認ツール")
st.write("PDFをアップロードすると、紙面内のQRコードを検出し、初期URLとリダイレクト先の最終URLをリストアップします。")

# PDFファイルのアップロード
uploaded_file = st.file_uploader("PDFファイルをアップロードしてください", type=["pdf"])

if uploaded_file is not None:
    results = []
    
    with st.spinner("PDFを解析・URLを確認中... しばらくお待ちください。"):
        # PDFを読み込む
        doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
        
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            # QRコードを認識しやすくするため、解像度を高め(dpi=300)で画像化
            pix = page.get_pixmap(dpi=300)
            img = Image.open(io.BytesIO(pix.tobytes()))
            
            # 画像からQRコードをデコード
            decoded_objects = decode(img)
            
            for obj in decoded_objects:
                qr_url = obj.data.decode('utf-8')
                final_url = ""
                status = "取得失敗"
                
                # リダイレクト先の確認
                if qr_url.startswith("http"):
                    try:
                        # 実際にアクセスして最終URLを取得 (timeoutを設定してフリーズを防ぐ)
                        response = requests.get(qr_url, timeout=10, allow_redirects=True)
                        final_url = response.url
                        status = f"{response.status_code}"
                    except requests.exceptions.RequestException as e:
                        final_url = f"アクセスエラー: {e}"
                else:
                    final_url = "URL形式ではありません"
                
                results.append({
                    "ページ": page_num + 1,
                    "QRコードの内容 (初期URL)": qr_url,
                    "リダイレクト先 (最終URL)": final_url,
                    "HTTPステータス": status
                })

    # 結果の表示
    if results:
        st.success(f"合計 {len(results)} 個のQRコードを検出しました。")
        # データを表（データフレーム）にして表示
        df = pd.DataFrame(results)
        st.dataframe(df, use_container_width=True)
        
        # CSVダウンロードボタンの追加
        csv = df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="CSVとしてダウンロード",
            data=csv,
            file_name='qr_codes_list.csv',
            mime='text/csv',
        )
    else:
        st.warning("このPDFからはQRコードが検出されませんでした。")