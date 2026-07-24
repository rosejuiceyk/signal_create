import streamlit as st

st.set_page_config(
    page_title="He-3 脉冲信号模拟系统",
    page_icon="⚛",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.sidebar.markdown("# ⚛ He-3 脉冲信号模拟")
st.sidebar.markdown("零功率反应堆中子噪声数字孪生")
st.sidebar.markdown("---")

page = st.navigation(
    {
        "事件生成": [
            st.Page("pages/01_event_generation.py", title="事件生成与统计", icon="📊"),
        ],
        "波形": [
            st.Page("pages/02_waveform.py", title="连续波形生成", icon="〰️"),
        ],
        "噪声分析": [
            st.Page("pages/03_phase_b.py", title="脉冲模式噪声分析", icon="📈"),
            st.Page("pages/04_phase_c.py", title="连续信号噪声分析", icon="🔬"),
        ],
    },
    position="sidebar",
)
page.run()
