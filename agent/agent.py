from typing import Annotated, Literal
from typing_extensions import TypedDict
from langgraph.graph import MessagesState, StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage

from .database import setup_db
from .prompt import SYSTEM_PROMPT
from .config import OPENAI_API_KEY

class State(TypedDict):
    messages: Annotated[list, add_messages]

def setup_memory():
    return MemorySaver()

def chatbot(state: State):
    return {"messages": llm_with_tools.invoke([SystemMessage(content=SYSTEM_PROMPT)] + state['messages'])}

def call_tools(state: MessagesState) -> Literal["tools", "END"]:
    """Check if tools need to be called and route accordingly."""
    messages = state["messages"]
    last_message = messages[-1]
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        return "tools"
    return END

def create_agent():
    # Define the LLM and tools
    llm = ChatOpenAI(model="gpt-4")
    db = setup_db()
    toolkit = SQLDatabaseToolkit(db=db, llm=llm)
    
    global tools, llm_with_tools
    tools = toolkit.get_tools()
    llm_with_tools = llm.bind_tools(tools)
    
    def create_sql_agent():
        return ToolNode(tools)

    # Build the graph
    graph_builder = StateGraph(State)
    
    # Add nodes
    graph_builder.add_node("chatbot", chatbot)
    graph_builder.add_node("sql_agent", create_sql_agent())
    
    # Add edges
    graph_builder.add_edge(START, "chatbot")
    graph_builder.add_conditional_edges(
        "chatbot",
        call_tools,
        {
            "tools": "sql_agent",
            END: END
        }
    )
    graph_builder.add_edge("sql_agent", "chatbot")
    
    # Compile and return graph
    return graph_builder.compile(checkpointer=setup_memory())