import streamlit as st
import datetime
import os
import json
import io
import PyPDF2
from google.oauth2 import service_account
from googleapiclient.discovery import build
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.tools.tavily_search import TavilySearchResults
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool
from dotenv import load_dotenv

# ==========================================
# 0. アプリケーション設定
# ==========================================
APP_VERSION = "1.8.0" # ★サブフォルダ＆スプレッドシート対応版

load_dotenv()

def load_password():
    try:
        with open("password.txt", "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "1234"

def load_instructions():
    try:
        with open("instructions.txt", "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "あなたは私の優秀なAI秘書です。丁寧に回答してください。"

MY_SECRET_PIN = load_password()
SYSTEM_RULES = load_instructions()

# ==========================================
# ★進化：ドライブ読み込みツール（サブフォルダ対応）
# ==========================================
@tool
def read_golf_drive_data() -> str:
    """Googleドライブの「ゴルフデータ」フォルダから、過去の反省点やスコアを読み込みます。"""
    try:
        creds_json_str = st.secrets.get("GCP_SERVICE_ACCOUNT") or os.environ.get("GCP_SERVICE_ACCOUNT")
        folder_id = st.secrets.get("DRIVE_FOLDER_ID") or os.environ.get("DRIVE_FOLDER_ID")
        
        if not creds_json_str or not folder_id:
            return "エラー：Googleドライブの連携設定がされていません。"

        creds_info = json.loads(creds_json_str)
        creds = service_account.Credentials.from_service_account_info(creds_info)
        service = build('drive', 'v3', credentials=creds)

        # ★追加：サブフォルダの中身も再帰的にすべて探し出す魔法の関数
        def get_files_recursive(current_folder_id):
            files_list = []
            results = service.files().list(
                q=f"'{current_folder_id}' in parents and trashed=false",
                fields="files(id, name, mimeType)"
            ).execute()
            
            for item in results.get('files', []):
                if item['mimeType'] == 'application/vnd.google-apps.folder':
                    # フォルダなら、その箱を開けてさらに中を探す
                    files_list.extend(get_files_recursive(item['id']))
                else:
                    # ファイルならリストに追加する
                    files_list.append(item)
            return files_list

        # 大元のフォルダIDから探索スタート
        items = get_files_recursive(folder_id)

        if not items:
            return "ドライブにデータが見つかりませんでした。"

        all_text = "【過去のゴルフデータ・反省点】\n"
        for item in items:
            all_text += f"\n--- {item['name']} ---\n"
            mime = item['mimeType']
            
            try:
                if mime == 'application/vnd.google-apps.document': # Googleドキュメント
                    request = service.files().export_media(fileId=item['id'], mimeType='text/plain')
                    downloaded = io.BytesIO(request.execute())
                    all_text += downloaded.read().decode('utf-8') + "\n"
                elif mime == 'application/vnd.google-apps.spreadsheet': # ★追加：スプレッドシート（表計算）
                    request = service.files().export_media(fileId=item['id'], mimeType='text/csv')
                    downloaded = io.BytesIO(request.execute())
                    all_text += downloaded.read().decode('utf-8') + "\n"
                else:
                    request = service.files().get_media(fileId=item['id'])
                    downloaded = io.BytesIO(request.execute())
                    
                    if mime == 'application/pdf': # PDF
                        reader = PyPDF2.PdfReader(downloaded)
                        for page in reader.pages:
                            text = page.extract_text()
                            if text:
                                all_text += text + "\n"
                    elif mime == 'text/plain' or mime == 'text/csv': # テキストやCSV
                        all_text += downloaded.read().decode('utf-8') + "\n"
                    else:
                        all_text += "（読み込めない形式のファイルです）\n"
            except Exception as file_e:
                all_text += f"（ファイル読み込みエラー: {str(file_e)}）\n"

        return all_text[:10000] # 一度に読める文字数を少し増やしました
    except Exception as e:
        return f"ドライブのアクセスでエラーが発生しました: {str(e)}"

# ==========================================
# 画面の表示
# ==========================================
st.markdown("#### ☀️ 私のAI秘書エージェント")
st.caption(f"バージョン: {APP_VERSION}")

st.sidebar.markdown("### 🔒 セキュリティロック")
entered_pin = st.sidebar.text_input("暗証番号を入力してください", type="password")

if entered_pin != MY_SECRET_PIN:
    st.warning("👈 左側のサイドバーに正しい暗証番号を入力してロックを解除してください。")
    st.stop()

st.sidebar.success("ロック解除成功！")

st.sidebar.markdown("---")
st.sidebar.markdown("### ⚡ クイックアクション")
weather_btn = st.sidebar.button("🌤️ 福山市の天気")
news_btn = st.sidebar.button("📰 最新ニュース")
carp_btn = st.sidebar.button("⚾ カープ情報")
golf_btn = st.sidebar.button("⛳ ゴルフコーチに相談")

if "messages" not in st.session_state:
    st.session_state.messages = []

google_api_key = os.environ.get("GOOGLE_API_KEY")
tavily_api_key = os.environ.get("TAVILY_API_KEY")

if google_api_key and tavily_api_key:
    JST = datetime.timezone(datetime.timedelta(hours=+9), 'JST')
    today_str = datetime.datetime.now(JST).strftime("%Y年%m月%d日")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    user_input = st.chat_input("AI秘書に指示を出してください")

    prompt = None
    if weather_btn:
        prompt = "今日の福山市の天気を、Yahoo!天気から時間ごとに調べて教えてください。"
    elif news_btn:
        prompt = "今日の政治、経済、スポーツのニュースを、Yahoo!ニュースから調べて教えてください。"
    elif carp_btn:
        prompt = "広島東洋カープの最新情報（試合結果や予定など）を調べて教えてください。"
    elif golf_btn:
        prompt = "Googleドライブのデータをすべて読み込んで、過去の反省点やスコアを踏まえた、次回の練習アドバイスを具体的に教えてください。"
    elif user_input:
        prompt = user_input

    if prompt:
        with st.chat_message("user"):
            st.write(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        with st.chat_message("assistant"):
            with st.spinner("情報を検索・分析しています（ドライブのサブフォルダも確認中）..."):
                llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
                search_tool = TavilySearchResults(max_results=5)
                agent_executor = create_react_agent(llm, [search_tool, read_golf_drive_data])

                chat_history = []
                for m in st.session_state.messages:
                    chat_history.append((m["role"], m["content"]))
                
                hidden_instructions = f"""
                今日は {today_str} です。
                【特別ルール】
                {SYSTEM_RULES}
                【私からの指示】
                {prompt}
                """
                
                chat_history[-1] = ("user", hidden_instructions)

                result = agent_executor.invoke({"messages": chat_history})
                
                final_content = result["messages"][-1].content
                response_text = final_content[0].get("text", "") if isinstance(final_content, list) else final_content
                st.write(response_text)

                st.session_state.messages.append({"role": "assistant", "content": response_text})
else:
    st.error("エラー：.envファイルにAPIキーが正しく設定されていません。")