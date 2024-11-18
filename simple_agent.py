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
import logging
from datetime import datetime
import json

# Configure logging
def setup_logging():
    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    # Configure logging with both file and console handlers
    log_filename = f'logs/rental_system_{datetime.now().strftime("%Y%m%d")}.log'
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filename),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()

warnings.filterwarnings('ignore', 
    category=sa_exc.SAWarning, 
    message='Cannot correctly sort tables.*'
)

load_dotenv()

os.environ["OPENAI_API_KEY"] = os.getenv('OPENAI_API_KEY')
logger.info("Environment variables loaded")

class State(TypedDict):
    messages: Annotated[list, add_messages]

def setup_memory():
    logger.info("Setting up memory")
    return MemorySaver()

def setup_db():
    logger.info("Setting up database connection")
    try:
        db_path = os.path.join(os.path.dirname(__file__), "rental.db")
        db = SQLDatabase.from_uri(f"sqlite:///{db_path}")
        logger.info("Database connection successful")
        return db
    except Exception as e:
        logger.error(f"Database connection failed: {str(e)}")
        raise

# Define the LLM and tools
llm = ChatOpenAI(model="gpt-4")
db = setup_db()
toolkit = SQLDatabaseToolkit(db=db, llm=llm)
tools = toolkit.get_tools()
llm_with_tools = llm.bind_tools(tools)
logger.info("LLM and tools initialized")

def chatbot(state: State):
    logger.info("Processing chatbot request")
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
    - For actor queries: join rental → inventory → film → film_actor → actor
    - For film queries: join rental → inventory → film
    - For customer queries: join rental → customer
    - For staff queries: join rental → staff
    
    3. When handling questions:
    a) If NOT related to DVD rental business:
        - Respond ONLY with: "I can only answer questions about the DVD rental business."
        
    b) If related to DVD rental business:
        - Use sql_db_schema to verify table structure if needed
        - Use sql_db_query_checker to validate your SQL query
        - Use sql_db_query to execute the validated query
        - ALWAYS include descriptive information (names, titles) in results
        - Format numbers appropriately (counts, amounts, etc.)

    Remember: 
    - No IDs in final responses, always show names/titles
    - Include proper joins to get all relevant information
    - Only answer DVD rental related questions
    """
    try:
        response = llm_with_tools.invoke([SystemMessage(content=prompt)] + state['messages'])
        logger.info("Chatbot response generated successfully")
        return {"messages": response}
    except Exception as e:
        logger.error(f"Error in chatbot function: {str(e)}")
        raise

def create_sql_agent():
    logger.info("Creating SQL agent")
    return ToolNode(tools)

def call_tools(state: MessagesState) -> Literal["tools", "END"]:
    logger.info("Checking if tools need to be called")
    messages = state["messages"]
    last_message = messages[-1]
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        logger.info("Tool calls detected")
        return "tools"
    logger.info("No tool calls detected")
    return END

def build_graph(State, memory):
    logger.info("Building graph")
    try:
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
        
        graph = graph_builder.compile(checkpointer=memory)
        logger.info("Graph built successfully")
        return graph
    except Exception as e:
        logger.error(f"Error building graph: {str(e)}")
        raise

# Build the graph
graph = build_graph(State, memory=setup_memory())
config = {"configurable": {"thread_id": "1"}}

# Modify the main loop
async def main():
    while True:
        user_input = input("User: ")
        if user_input.lower() in ["quit", "q"]:
            print("Good Bye")
            break
        
        try:
            responses = []
            async for chunk in graph.astream({'messages': [HumanMessage(content=user_input)]}, config, stream_mode="values"):
                message = chunk["messages"][-1]
                content = message.content if hasattr(message, 'content') else str(message)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                
                conversation = {
                    "timestamp": timestamp,
                    "user": user_input,
                    "assistant": content
                }
                responses.append(conversation)
                message.pretty_print()
                logger.info(message)
            
            # Create folder if not exists
            if not os.path.exists('conversations'):
                os.makedirs('conversations')
                
            # Save with timestamp in filename
            filename = f'conversations/conversation_{timestamp}.json'
            with open(filename, 'w') as f:
                json.dump(responses[-1], f, indent=2)
                
        except Exception as e:
            print(f"Error: {str(e)}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())