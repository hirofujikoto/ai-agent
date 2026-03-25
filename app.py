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
APP_VERSION = "2.0.0" # ★履歴保存 ＆ ローカルファイル直接読み込み ＆ 待機モード版

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
# ★進化1：会話履歴のオートセーブ（保存と読み込み）
# ==========================================
HISTORY_FILE = "chat_history.json"

def load_chat_history():
    """保存された会話履歴を読み込む"""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    return []

def save_chat_history(messages):
    """会話履歴をファイルに保存する"""
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)

# ==========================================
# ツール1：Googleドライブ読み込み（前回作成した超高速版）
# ==========================================
@st.cache_data(ttl=3600)
def fetch_all_drive_data(creds_json_str, folder_id):
    creds_info = json.loads(creds_json_str)
    creds = service_account.Credentials.from_service_account_info(creds_info)
    service = build('drive', 'v3', credentials=creds)

    def get_files_recursive(current_folder_id):
        files_list = []
        results = service.files().list(
            q=f"'{current_folder_id}' in parents and trashed=false",
            fields="files(id, name, mimeType)"
        ).execute()
        for item in results.get('files', []):
            if item['mimeType'] == 'application/vnd.google-apps.folder':
                files_list.extend(get_files_recursive(item['id']))
            else:
                files_list.append(item)
        return files_list

    items = get_files_recursive(folder_id)
    if not items:
        return "ドライブにデータが見つかりませんでした。"

    all_text = "【Googleドライブ内の過去データ】\n"
    for item in items:
        all_text += f"\n--- {item['name']} ---\n"
        mime = item['mimeType']
        try:
            if mime == 'application/vnd.google-apps.document':
                request = service.files().export_media(fileId=item['id'], mimeType='text/plain')
                all_text += io.BytesIO(request.execute()).read().decode('utf-8') + "\n"
            elif mime == 'application/vnd.google-apps.spreadsheet':
                request = service.files().export_media(fileId=item['id'], mimeType='text/csv')
                all_text += io.BytesIO(request.execute()).read().decode('utf-8') + "\n"
            else:
                request = service.files().get_media(fileId=item['id'])
                downloaded = io.BytesIO(request.execute())
                if mime == 'application/pdf':
                    for page in PyPDF2.PdfReader(downloaded).pages:
                        if page.extract_text(): all_text += page.extract_text() + "\n"
                elif mime in ['text/plain', 'text/csv']:
                    all_text += downloaded.read().decode('utf-8') + "\n"
        except:
            pass
    return all_text[:8000]

@tool
def read_golf_drive_data() -> str:
    """Googleドライブの「ゴルフデータ」フォルダから、過去の反省点を読み込みます。"""
    creds_json_str = st.secrets.get("GCP_SERVICE_ACCOUNT") or os.environ.get("GCP_SERVICE_ACCOUNT")
    folder_id = st.secrets.get("DRIVE_FOLDER_ID") or os.environ.get("DRIVE_FOLDER_ID")
    if not creds_json_str or not folder_id: return "エラー：Googleドライブの設定がありません。"
    return fetch_all_drive_data(creds_json_str, folder_id)

# ==========================================
# ★進化2：アプリと同じ場所にあるファイルを直接読むツール
# ==========================================
@tool
def read_local_app_data() -> str:
    """アプリと同じ場所（GitHub上）に保存されている、ゴルフの実績スコアなどのテキストやCSVファイルを直接読み込みます。"""
    all_text = "【アプリ内の実績スコアデータ】\n"
    try:
        # アプリのフォルダ内にあるファイルをすべて確認
        for filename in os.listdir('.'):
            # システム関係のファイル（app.pyなど）は除外して、テキストやCSVだけを読む
            if filename.endswith('.csv') or filename.endswith('.txt'):
                if filename not in ['app.py', 'requirements.txt', 'instructions.txt', 'password.txt']:
                    with open(filename, 'r', encoding='utf-8') as file:
                        all_text += f"\n--- {filename} ---\n"
                        all_text += file.read()[:2000] + "\n"
        return all_text
    except Exception as e:
        return f"ローカルファイルの読み込みエラー: {str(e)}"

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

# ==========================================
# 会話履歴の復元
# ==========================================
if "messages" not in st.session_state:
    st.session_state.messages = load_chat_history() # ★ファイルから記憶を呼び出す

st.sidebar.success("ロック解除成功！")
# ★追加：記憶を消去するリセットボタン
if st.sidebar.button("🗑️ 会話の記憶をリセット"):
    st.session_state.messages = []
    save_chat_history([])
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("### ⚡ クイックアクション")
weather_btn = st.sidebar.button("🌤️ 福山市の天気")
news_btn = st.sidebar.button("📰 最新ニュース")
carp_btn = st.sidebar.button("⚾ カープ情報")
golf_btn = st.sidebar.button("⛳ ゴルフデータを読み込む") # ★ボタン名も変更

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
        # ★進化3：勝手にアドバイスせず、待機するように指示を変更
        prompt = "Googleドライブ内の過去の反省点データと、アプリ内にある実績スコアデータをすべて読み込んで内容を把握してください。その後、勝手にアドバイスは行わず、「データの読み込みと内容の把握が完了しました。どのような分析やご相談をご希望ですか？」とだけ返答して待機してください。"
    elif user_input:
        prompt = user_input

    if prompt:
        with st.chat_message("user"):
            st.write(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        with st.chat_message("assistant"):
            with st.spinner("情報を処理しています..."):
                llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
                search_tool = TavilySearchResults(max_results=5)
                # ★変更：アプリ内のファイルを読むツール(read_local_app_data)を追加！
                agent_executor = create_react_agent(llm, [search_tool, read_golf_drive_data, read_local_app_data])

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

                # ★回答を履歴に追加して、ファイルにセーブ！
                st.session_state.messages.append({"role": "assistant", "content": response_text})
                save_chat_history(st.session_state.messages)

else:
    st.error("エラー：.envファイルにAPIキーが正しく設定されていません。")