import streamlit as st
from langchain_core.messages import HumanMessage
from agent.agent import create_agent

import streamlit as st
from langchain_core.messages import HumanMessage
from agent.agent import create_agent

def main():
    st.title("DVD Rental Query Assistant")
    
    # Initialize session state for chat history ONCE
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = [
            {
                "role": "assistant", 
                "content": "Hello! I'm your DVD rental assistant. How can I help you today?"
            }
        ]
    
    if "agent" not in st.session_state:
        st.session_state.agent = create_agent()
        
    # Config for the agent
    config = {"configurable": {"thread_id": "1"}}
    
    # Display chat history ONCE
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Chat input
    if prompt := st.chat_input("Ask a question about DVD rentals"):
        # Display user message
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Add user message to chat history
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        
        # Get bot response
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    final_response = None
                    for event in st.session_state.agent.stream(
                        {'messages': [HumanMessage(content=prompt)]}, 
                        config
                    ):
                        for value in event.values():
                            if hasattr(value["messages"], "content"):
                                final_response = value["messages"].content
                    
                    if final_response:
                        st.markdown(final_response)
                        # Add assistant message to chat history
                        st.session_state.chat_history.append(
                            {"role": "assistant", "content": final_response}
                        )
                except Exception as e:
                    st.error(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    main()