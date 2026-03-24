import streamlit as st
import datetime
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.tools.tavily_search import TavilySearchResults
from langgraph.prebuilt import create_react_agent
from dotenv import load_dotenv

# ==========================================
# 0. アプリケーション設定（バージョンなど）
# ==========================================
APP_VERSION = "1.0.0" # ★ここでバージョン番号を管理します

# パスワードとAPIキーの自動読み込み
load_dotenv()

def load_password():
    try:
        with open("password.txt", "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "1234"

MY_SECRET_PIN = load_password()

# ==========================================
# 画面の表示（タイトルとバージョン）
# ==========================================
st.markdown("#### ☀️ 私のAI秘書エージェント")
st.caption(f"バージョン: {APP_VERSION}") # ★タイトルの下に小さくバージョンを表示します

st.sidebar.markdown("### 🔒 セキュリティロック")
entered_pin = st.sidebar.text_input("暗証番号を入力してください", type="password")

if entered_pin != MY_SECRET_PIN:
    st.warning("👈 左側のサイドバーに正しい暗証番号を入力してロックを解除してください。")
    st.stop()

# ==========================================
# 1. 初期設定（ロック解除後に初めて表示される）
# ==========================================
st.sidebar.success("ロック解除成功！")

if "messages" not in st.session_state:
    st.session_state.messages = []

# ==========================================
# 2. エージェントの実行とチャット画面
# ==========================================
google_api_key = os.environ.get("GOOGLE_API_KEY")
tavily_api_key = os.environ.get("TAVILY_API_KEY")

if google_api_key and tavily_api_key:
    today_str = datetime.date.today().strftime("%Y年%m月%d日")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    user_input = st.chat_input("AI秘書に指示を出してください")

    if user_input:
        with st.chat_message("user"):
            st.write(user_input)
        st.session_state.messages.append({"role": "user", "content": user_input})

        with st.chat_message("assistant"):
            with st.spinner("情報を集めています..."):
                llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
                search_tool = TavilySearchResults(max_results=3)
                agent_executor = create_react_agent(llm, [search_tool])

                chat_history = []
                for m in st.session_state.messages:
                    chat_history.append((m["role"], m["content"]))
                
                chat_history[-1] = ("user", f"今日は {today_str} です。以下の指示を実行してください：\n{user_input}")

                result = agent_executor.invoke({"messages": chat_history})
                
                final_content = result["messages"][-1].content
                response_text = final_content[0].get("text", "") if isinstance(final_content, list) else final_content
                st.write(response_text)

                st.session_state.messages.append({"role": "assistant", "content": response_text})

else:
    st.error("エラー：.envファイルにAPIキーが正しく設定されていません。")