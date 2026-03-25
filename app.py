import streamlit as st
import datetime
import os
import PyPDF2  # ★追加：PDFを解読するための道具
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.tools.tavily_search import TavilySearchResults
from langgraph.prebuilt import create_react_agent
from dotenv import load_dotenv

# ==========================================
# 0. アプリケーション設定
# ==========================================
APP_VERSION = "1.6.0" # ★ファイル読み込み機能追加版

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
# 画面の表示（タイトルとバージョン）
# ==========================================
st.markdown("#### ☀️ 私のAI秘書エージェント")
st.caption(f"バージョン: {APP_VERSION}")

st.sidebar.markdown("### 🔒 セキュリティロック")
entered_pin = st.sidebar.text_input("暗証番号を入力してください", type="password")

if entered_pin != MY_SECRET_PIN:
    st.warning("👈 左側のサイドバーに正しい暗証番号を入力してロックを解除してください。")
    st.stop()

st.sidebar.success("ロック解除成功！")

# ==========================================
# ★追加：ゴルフデータなどのファイル投入口
# ==========================================
st.sidebar.markdown("---")
st.sidebar.markdown("### ⛳ データ読み込み")
uploaded_file = st.sidebar.file_uploader("テキストやPDFをアップロード", type=["txt", "pdf"])

file_content = ""
if uploaded_file is not None:
    # テキストファイルの場合
    if uploaded_file.type == "text/plain":
        file_content = uploaded_file.read().decode("utf-8")
        st.sidebar.success("テキストデータを読み込みました！")
    # PDFファイルの場合
    elif uploaded_file.type == "application/pdf":
        pdf_reader = PyPDF2.PdfReader(uploaded_file)
        for page in pdf_reader.pages:
            extracted = page.extract_text()
            if extracted:
                file_content += extracted + "\n"
        st.sidebar.success("PDFデータを読み込みました！")

# ==========================================
# クイックアクションボタン
# ==========================================
st.sidebar.markdown("---")
st.sidebar.markdown("### ⚡ クイックアクション")
weather_btn = st.sidebar.button("🌤️ 福山市の天気")
news_btn = st.sidebar.button("📰 最新ニュース")
carp_btn = st.sidebar.button("⚾ カープ情報")

if "messages" not in st.session_state:
    st.session_state.messages = []

# ==========================================
# エージェントの実行
# ==========================================
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
    elif user_input:
        prompt = user_input

    if prompt:
        with st.chat_message("user"):
            st.write(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        with st.chat_message("assistant"):
            with st.spinner("情報を検索・分析しています..."):
                llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
                search_tool = TavilySearchResults(max_results=5) # エラー防止のため5件に設定
                agent_executor = create_react_agent(llm, [search_tool])

                chat_history = []
                for m in st.session_state.messages:
                    chat_history.append((m["role"], m["content"]))
                
                # ★追加：読み込んだファイルの中身をAIにこっそり渡す
                file_instruction = ""
                if file_content:
                    file_instruction = f"\n\n【読み込んだファイルデータ】\n以下のデータを参考にして回答してください：\n{file_content}\n"

                hidden_instructions = f"""
                今日は {today_str} です。

                【特別ルール】
                {SYSTEM_RULES}
                {file_instruction}

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