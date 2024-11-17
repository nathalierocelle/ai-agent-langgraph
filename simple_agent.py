from typing import Annotated, Literal
from typing_extensions import TypedDict
from langgraph.graph import MessagesState
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode
from langchain_community.utilities.sql_database import SQLDatabase
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from dotenv import load_dotenv
import os
import warnings
from sqlalchemy import exc as sa_exc


warnings.filterwarnings('ignore', 
    category=sa_exc.SAWarning, 
    message='Cannot correctly sort tables.*'
)

load_dotenv()

os.environ["OPENAI_API_KEY"] = os.getenv('OPENAI_API_KEY')

class State(TypedDict):
    messages: Annotated[list, add_messages]

def setup_memory():
    return MemorySaver()

def setup_db():
    db_path = os.path.join(os.path.dirname(__file__), "rental.db")
    return SQLDatabase.from_uri(f"sqlite:///{db_path}")

# Define the LLM and tools first
llm = ChatOpenAI(model="gpt-4")
db = setup_db()
toolkit = SQLDatabaseToolkit(db=db, llm=llm)
tools = toolkit.get_tools()
llm_with_tools = llm.bind_tools(tools)

def chatbot(state: State):
    prompt = """
    You are a helpful assistant tasked with validating user queries related to DVD rental data. Your primary role is to:

    1. ONLY answer questions related to DVD rental business data using this schema:
       - film: film_id, title, description, release_year, language_id, rental_duration, rental_rate, length, replacement_cost, rating
       - actor: actor_id, first_name, last_name
       - film_actor: film_id, actor_id
       - customer: customer_id, first_name, last_name, email, address_id
       - rental: rental_id, rental_date, inventory_id, customer_id, return_date, staff_id
       - inventory: inventory_id, film_id, store_id
       - payment: payment_id, customer_id, staff_id, rental_id, amount, payment_date
       - staff: staff_id, first_name, last_name, address_id, email, store_id, username
       - store: store_id, manager_staff_id, address_id
       
    2. When writing queries:
       - ALWAYS join with appropriate tables to show names instead of IDs
       - DO NOT make any DML statements (INSERT, UPDATE, DELETE, DROP etc.) to the database.
       - You MUST double check your query before executing it. If you get an error while executing a query, rewrite the query and try again.
       
    3. When handling questions:
       a) If NOT related to DVD rental business:
          - Respond ONLY with: "Apologies. I can only answer questions about the DVD rental business."
          
       b) If related to DVD rental business:
          - Use sql_db_schema to verify table structure if needed
          - Use sql_db_query_checker to validate your SQL query
          - Use sql_db_query to execute the validated query
          - ALWAYS include descriptive information (names, titles) in results
          - Format numbers appropriately (counts, amounts, etc.)

    """
    return {"messages": llm_with_tools.invoke([SystemMessage(content=prompt)] + state['messages'])}

def create_sql_agent():
    return ToolNode(tools)

def call_tools(state: MessagesState) -> Literal["tools", "END"]:
    """Check if tools need to be called and route accordingly."""
    messages = state["messages"]
    last_message = messages[-1]
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        return "tools"
    return END

def build_graph(State, memory):
    graph_builder = StateGraph(State)
    
    # Add nodes
    graph_builder.add_node("chatbot", chatbot)
    graph_builder.add_node("sql_agent", create_sql_agent())
    
    # Add base edges
    graph_builder.add_edge(START, "chatbot")
    
    # Add conditional routing from chatbot
    graph_builder.add_conditional_edges(
        "chatbot",
        call_tools,
        {
            "tools": "sql_agent",  # If tools needed, go to SQL agent
            END: END               # If no tools needed, end the sequence
        }
    )
    
    # After using tools, return to chatbot
    graph_builder.add_edge("sql_agent", "chatbot")
    
    # Compile graph
    graph = graph_builder.compile(checkpointer=memory) 
    return graph

# Build the graph
graph = build_graph(State, memory=setup_memory())

# Setup the config thread of memory
config = {"configurable": {"thread_id": "1"}}

# while True:
#     user_input = input("User: ")
#     if user_input.lower() in ["quit", "q"]:
#         print("Good Bye")
#         break
#     try:
#         for event in graph.stream({'messages': [HumanMessage(content=user_input)]}, config):
#             for value in event.values():
#                 if hasattr(value["messages"], "content"):
#                     print("Assistant:", value["messages"].content)
#                 else:
#                     print("Assistant:", str(value["messages"]))
#     except Exception as e:
#         print(f"An error occurred: {str(e)}")

while True:
    user_input = input("User: ")
    if user_input.lower() in ["quit", "q"]:
        print("Good Bye")
        break
    try:
        final_response = None
        for event in graph.stream({'messages': [HumanMessage(content=user_input)]}, config):
            for value in event.values():
                if hasattr(value["messages"], "content"):
                    final_response = value["messages"].content
        if final_response:
            print("Assistant:", final_response)
                    
    except Exception as e:
        print(f"An error occurred: {str(e)}")