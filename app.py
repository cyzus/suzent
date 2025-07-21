
import streamlit as st
import requests
import json
import re

st.title("SMOL Agent UI")

CODE_TAG = "<code>"

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("What is up?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        final_answer = ""
        with st.status("Thinking...", expanded=True) as status:
            try:
                with requests.post("http://localhost:8000/chat", json={"message": prompt}, stream=True) as r:
                    r.raise_for_status()
                    is_streaming = False
                    streaming_content = ""
                    code_content = ""
                    for chunk in r.iter_content(chunk_size=None):
                        if chunk:
                            try:
                                data = json.loads(chunk)
                                response_type = data.get("type")
                                response_data = data.get("data")
                                
                                if response_type == "stream_delta":
                                    content = response_data.get("content", "")
                                    if content:
                                        if CODE_TAG not in content and not code_content:
                                            is_streaming = True
                                            streaming_content += content
                                            st.write(content)
                                        else:
                                            code_index = content.find(CODE_TAG)
                                            if code_index != -1:
                                                content_for_stream = content[:content.index(CODE_TAG)]
                                                streaming_content += content_for_stream
                                                if content_for_stream:
                                                    st.write(content_for_stream)
                                                code_content += content[content.index(CODE_TAG) + len(CODE_TAG):]
                                            else:
                                                code_content += content
                                else:
                                    if code_content:
                                        st.code(code_content)
                                        code_content = ""
                                    is_streaming = False
                                    streaming_content = ""
                                    
                                    if response_type == "final_answer":
                                        final_answer = response_data
                                        status.update(label="Done!", state="complete", expanded=False)
                                    elif response_type == "action":
                                        observations = response_data["observations"]
                                        if observations and not response_data["is_final_answer"]:
                                            st.markdown(
                                                f"""
                                                <div style="background-color:#f9f6e7; border-left: 6px solid #f7c873; padding: 12px; margin: 10px 0; border-radius: 6px;">
                                                    <strong>Observations:</strong><br>
                                                    {observations}
                                                </div>
                                                """,
                                                unsafe_allow_html=True
                                            )
                                        
                                    elif response_type == "other" and isinstance(response_data, str) and response_data.startswith("ToolCall"):
                                        match = re.search(r"name='([^']*)'", response_data)
                                        if match:
                                            tool_name = match.group(1)
                                            st.write(f"*Tool: `{tool_name}`*")
                            except json.JSONDecodeError:
                                # Handle cases where a chunk is not a valid JSON object
                                pass
            except requests.exceptions.RequestException as e:
                st.error(f"Error connecting to the server: {e}")
        st.markdown(final_answer)
        st.session_state.messages.append({"role": "assistant", "content": final_answer})
