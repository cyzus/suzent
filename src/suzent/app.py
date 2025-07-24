import json
import re
from pathlib import Path

import requests
import streamlit as st

from suzent.config import Config

# --- Page Configuration ---
st.set_page_config(
    page_title=Config.TITLE,
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Constants ---
SERVER_URL = Config.SERVER_URL
CODE_TAG = Config.CODE_TAG
MCP_URLS_FILE = Path("mcp_urls.json")


# --- MCP URL Persistence ---
def load_mcp_urls():
    """Loads MCP URLs from the JSON file."""
    if MCP_URLS_FILE.exists():
        with open(MCP_URLS_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []  # Return empty list if file is corrupted
    # Default URLs if file doesn't exist
    return [
        {"name": f"Default Server {i+1}", "url": url.strip()}
        for i, url in enumerate(Config.DEFAULT_MCP_URLS.split(","))
        if url.strip()
    ]


def save_mcp_urls(servers):
    """Saves MCP URLs to the JSON file."""
    with open(MCP_URLS_FILE, "w") as f:
        # Save only name and url, not the enabled state
        servers_to_save = [{"name": s["name"], "url": s["url"]} for s in servers]
        json.dump(servers_to_save, f, indent=2)


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
    st.title(Config.TITLE)

    # --- Sidebar ---
    st.sidebar.title("Configuration")

    # Model selection
    model_options = Config.MODEL_OPTIONS
    selected_model = st.sidebar.selectbox("Select Model", model_options, index=0)

    # Agent selection
    agent_options = Config.AGENT_OPTIONS
    selected_agent = st.sidebar.selectbox("Select Agent", agent_options, index=0)

    # Tool selection
    tool_options = Config.TOOL_OPTIONS
    selected_tools = st.sidebar.multiselect("Select Tools", tool_options, default=Config.DEFAULT_TOOLS)

    st.sidebar.title("MCP Configuration")

    # Initialize mcp_servers in session state if not present
    if "mcp_servers" not in st.session_state:
        servers = load_mcp_urls()
        st.session_state.mcp_servers = [
            {"name": s["name"], "url": s["url"], "enabled": True} for s in servers
        ]

    # Input for adding a new MCP URL
    st.sidebar.markdown("Add New MCP Server")
    new_mcp_name = st.sidebar.text_input("Server Name", key="new_mcp_name_input")
    new_mcp_url = st.sidebar.text_input("Server URL", key="new_mcp_url_input")

    if st.sidebar.button("Add MCP") and new_mcp_name and new_mcp_url:
        if not any(s["url"] == new_mcp_url for s in st.session_state.mcp_servers):
            st.session_state.mcp_servers.append(
                {"name": new_mcp_name, "url": new_mcp_url, "enabled": True}
            )
            save_mcp_urls(st.session_state.mcp_servers)
            st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.markdown("**Registered MCP Servers**")

    # Display and manage existing MCP servers
    indices_to_remove = []
    for i, server in enumerate(st.session_state.mcp_servers):
        cols = st.sidebar.columns([0.1, 0.7, 0.2])
        server["enabled"] = cols[0].checkbox(
            "", server["enabled"], key=f"mcp_enabled_{i}", label_visibility="collapsed"
        )
        cols[1].write(f"**{server['name']}**: `{server['url']}`")
        if cols[2].button("X", key=f"mcp_remove_{i}"):
            indices_to_remove.append(i)

    if indices_to_remove:
        st.session_state.mcp_servers = [
            s for i, s in enumerate(st.session_state.mcp_servers) if i not in indices_to_remove
        ]
        save_mcp_urls(st.session_state.mcp_servers)
        st.rerun()

    # Collect enabled MCP URLs to be used by the agent
    mcp_urls = [s["url"] for s in st.session_state.mcp_servers if s["enabled"]]

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
                    observations = re.sub(r"^Execution logs:\s*", "", observations.strip())
                    split_result = re.split(r"Last output from code snippet:\s*", observations)
                    observations = split_result[0].rstrip()
                    last_output_from_code = split_result[1] if len(split_result) > 1 else ""
                    full_response += f"\n\n<div style='background-color:#f9f6e7; border-left: 6px solid #f7c873; padding: 12px; margin: 10px 0; border-radius: 6px;'><strong>📝 Execution Logs</strong><br>{observations}</div>"
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