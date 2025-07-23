"""
This module implements a Streamlit-based user interface for interacting with a code-generating agent.

It provides a chat-like interface where users can send messages to the agent and receive real-time
responses. The UI handles various types of messages from the agent, including streaming text,
code blocks, tool usage, and final answers, displaying them in a structured and readable format.
"""

import json
import re

import requests
import streamlit as st

TITLE = "SUZ AGENT"

# --- Page Configuration ---
st.set_page_config(
    page_title=TITLE,
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Constants ---
SERVER_URL = "http://localhost:8000/chat"
CODE_TAG = "<code>"


# --- UI Components ---
def render_message(message):
    """
    Renders a single message in the chat interface, handling different roles and content types.
    """
    with st.chat_message(message["role"]):
        st.markdown(message["content"], unsafe_allow_html=True)


# --- Main Application Logic ---
def main():
    """
    Main function to run the Streamlit application.
    """
    st.title(TITLE)

    # --- Sidebar ---
    st.sidebar.title("Configuration")

    # Model selection
    model_options = [
        "gemini/gemini-2.5-flash",
        "gemini/gemini-2.5-pro",
        "anthropic/claude-sonnet-4-20250514",
        "openai/gpt-4.1",
        "deepseek/deepseek-chat"
    ]
    selected_model = st.sidebar.selectbox("Select Model", model_options, index=0)

    # Agent selection
    agent_options = ["CodeAgent"]
    selected_agent = st.sidebar.selectbox("Select Agent", agent_options, index=0)

    # Tool selection
    tool_options = ["WebSearchTool"]
    selected_tools = st.sidebar.multiselect("Select Tools", tool_options, default=["WebSearchTool"])

    mcp_urls_str = st.sidebar.text_area(
        "MCP URLs (comma-separated)", "https://evalstate-hf-mcp-server.hf.space/mcp"
    )
    mcp_urls = [url.strip() for url in mcp_urls_str.split(",") if url.strip()]

    if "messages" not in st.session_state:
        st.session_state.messages = []

    if st.sidebar.button("New Chat"):
        st.session_state.messages = []
        st.rerun()

    for message in st.session_state.messages:
        render_message(message)

    if prompt := st.chat_input("What is up?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        render_message({"role": "user", "content": prompt})

        with st.chat_message("assistant"):
            process_agent_response(
                prompt,
                config={
                    "model": selected_model,
                    "agent": selected_agent,
                    "tools": selected_tools,
                    "mcp_urls": mcp_urls,
                },
            )


def process_agent_response(prompt, config, reset: bool = False):
    """
    Processes the user's prompt, sends it to the agent, and displays the response.
    """
    placeholder = st.empty()
    full_response = ""
    is_in_code_block = False

    try:
        with requests.post(
            SERVER_URL,
            json={"message": prompt, "reset": reset, "config": config},
            stream=True,
            timeout=600,
        ) as r:
            r.raise_for_status()
            for chunk in r.iter_lines():
                if chunk:
                    full_response, is_in_code_block = handle_stream_chunk(
                        chunk, placeholder, full_response, is_in_code_block
                    )

    except requests.exceptions.RequestException as e:
        st.error(f"Error connecting to the server: {e}")
        return

    if full_response:
        st.session_state.messages.append({"role": "assistant", "content": full_response})
        # Final render to clean up any open code blocks
        # if is_in_code_block:
        #     full_response += "\n```\n"
        placeholder.markdown(full_response, unsafe_allow_html=True)


def handle_stream_chunk(chunk, placeholder, full_response, is_in_code_block):
    """
    Handles a single chunk from the streaming response, parsing and displaying it.
    """
    try:
        data_str = chunk.decode('utf-8').strip()
        if data_str.startswith("data:"):
            data_str = data_str[len("data:") :].strip()

        if not data_str:
            return full_response, is_in_code_block

        data = json.loads(data_str)
        response_type = data.get("type")
        response_data = data.get("data")

        if response_type == "stream_delta":
            content = response_data.get("content")
            if content:
                if not is_in_code_block:
                    if CODE_TAG in content:
                        before, _, after = content.partition(CODE_TAG)
                        full_response += before
                        full_response += f"\n```\n{after}"
                        is_in_code_block = True
                    else:
                        full_response += content
                else:
                    full_response += content
        else:
            if is_in_code_block:
                full_response += "\n```\n"
                is_in_code_block = False

            if response_type == "final_answer":
                final_answer = response_data
                full_response += f"\n\n{final_answer}"
            elif response_type == "action":
                observations = response_data.get("observations")
                if observations and not response_data.get("is_final_answer"):
                    full_response += f"\n\n<div style='background-color:#f9f6e7; border-left: 6px solid #f7c873; padding: 12px; margin: 10px 0; border-radius: 6px;'><strong>Observations:</strong><br>{observations}</div>"
            elif response_type == "other" and isinstance(response_data, str):
                match = re.search(r"name='([^']*)'", response_data)
                if match:
                    tool_name = match.group(1)
                    full_response += f"\n\n*Tool: `{tool_name}`*"
        placeholder.markdown(full_response, unsafe_allow_html=True)

    except json.JSONDecodeError:
        pass

    return full_response, is_in_code_block


if __name__ == "__main__":
    main()