# app.py
import streamlit as st
# from st_keyup import st_keyup
 
from datetime import datetime
from typing import Dict, List
import tempfile
import os
from PIL import Image
import io
import random
from pathlib import Path
from agent import create_thread, get_history, send_message, send_image_file

# Get the directory of your current script
current_dir = Path(__file__).parent
image_path = current_dir / "BioReact - Nick Art.png"
# ---------- Page config ----------
st.set_page_config(page_title="NickAI", page_icon="🌱", layout="wide")

# ---------- Session state bootstrapping ----------
if "thread_id" not in st.session_state:
    # Use existing thread if you have one; else create a new one
    st.session_state.thread_id = create_thread()

if "messages" not in st.session_state:
    # Normalize history into this app's structure
    history = get_history(st.session_state.thread_id)  # [{role, content}]
    st.session_state.messages: List[Dict] = []  
    for item in history:
        st.session_state.messages.append(
            {
                "id": len(st.session_state.messages) + 1,
                "content": item.get("content", ""),
                "type": "text",
                "sender": "user" if item.get("role") == "user" else "assistant",
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "image": None,
            }
        )

if "message_id" not in st.session_state:
    st.session_state.message_id = len(st.session_state.messages)

if "pending_upload" not in st.session_state:
    st.session_state.pending_upload = None

# ---------- Helpers ----------
def add_message(content: str, message_type: str = "text", sender: str = "user", image=None):
    st.session_state.message_id += 1
    st.session_state.messages.append(
        {
            "id": st.session_state.message_id,
            "content": content,
            "type": message_type,
            "sender": sender,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "image": image,
        }
    )

def display_message(message: Dict):
    if message["sender"] == "user":
        with st.chat_message("user"):
            if message["type"] == "image" and message["image"] is not None:
                # Display the image
                try:
                    if isinstance(message["image"], str):
                        # If it's a file path or base64 string
                        st.image(message["image"], caption="Imagen enviada", width=300)
                    else:
                        # If it's an uploaded file object
                        image = Image.open(message["image"])
                        st.image(image, caption="Imagen enviada", width=300)
                except Exception as e:
                    st.error(f"Error displaying image: {e}")
                    
                # Display any accompanying text
                if message["content"] and message["content"] != "(Imagen adjunta)":
                    st.write(message["content"])
            elif message["type"] == "text":
                st.write(message["content"])
                
            st.caption(f"🕐 {message['timestamp']}")
    else:
        with st.chat_message("assistant", avatar="🌱"):
            st.write(message["content"])
            st.caption(f"🕐 {message['timestamp']}")

def process_image_and_text(uploaded_file, text_input):
    """Process image upload and text together"""
    responses = []
    
    # Create a temporary file for the image
    if uploaded_file is not None:
        # Get file extension
        file_extension = os.path.splitext(uploaded_file.name)[1].lower()
        if not file_extension:
            file_extension = ".png"
            
        # Create temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as tmp_file:
            # Write uploaded file content to temp file
            tmp_file.write(uploaded_file.getbuffer())
            tmp_path = tmp_file.name
        
        try:
            # Add user message with image
            add_message(
                content=text_input if text_input else "Por favor analiza esta imagen.",
                message_type="image",
                sender="user",
                image=uploaded_file
            )
            
            # Send to assistant
            replies = send_image_file(
                thread_id=st.session_state.thread_id,
                text=text_input if text_input else "Por favor analiza esta imagen.",
                file_path=tmp_path,
                assistant_id=os.getenv("ASSISTANT_ID"),
            )
            
            # Add assistant responses
            for reply in replies:
                add_message(reply, "text", "assistant")
                responses.append(reply)
                
        except Exception as e:
            error_msg = f"⚠️ Error al procesar la imagen: {str(e)}"
            add_message(error_msg, "text", "assistant")
            responses.append(error_msg)
        finally:
            # Clean up temp file
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
    
    return responses

def process_text_only(text_input):
    """Process text-only message"""
    responses = []
    
    try:
        # Add user message
        add_message(text_input, "text", "user")
        
        # Send to assistant
        replies = send_message(
            thread_id=st.session_state.thread_id,
            message=text_input,
        )
        
        # Add assistant responses
        for reply in replies:
            add_message(reply, "text", "assistant")
            responses.append(reply)
            
    except Exception as e:
        error_msg = f"⚠️ Error al procesar el mensaje: {str(e)}"
        add_message(error_msg, "text", "assistant")
        responses.append(error_msg)
    
    return responses

# ---------- UI ----------

# Initialize input clearing mechanism
if "input_key" not in st.session_state:
    st.session_state.input_key = 0

if "clear_inputs" not in st.session_state:
    st.session_state.clear_inputs = False

st.session_state.setdefault("started", False)
if not st.session_state.started:
    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        # make a small 3-col grid inside the middle column and use the center one
        ic1, ic2, ic3 = st.columns([1, 8, 1])
        with ic2:
            try:
                img = Image.open(image_path)  # ensure the file is in your app's working dir
                st.image(img, use_container_width=True)
            except FileNotFoundError:
                st.info("Image not found")

        greetings = [
            "Hi, I'm Nick! Are you having trouble with your plants?",
            "Hi, my name is Nick! Are pests affecting your garden, vegetable garden, or crops?",
            "Hi, I'm Nick! I'll help you diagnose diseases in your plants.",
            "Hi, my name is Nick! I'll help you get rid of the insects on your plants.",
            "Hi, my name is Nick! Find out which pest is affecting your plants."
        ]


        st.markdown(
            f"<h2 style='text-align:center;'>{random.choice(greetings)}</h2>",
            unsafe_allow_html=True
        )

        # center the button in the middle column too
        bcol1, bcol2, bcol3 = st.columns([1, 2, 1])
        with bcol2:
            st.markdown("""
            <style>
            .stButton > button {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                border: none;
                padding: 10px 24px;
                border-radius: 4px;
                font-size: 20px;
            }
            .stButton > button:hover {
                background-color: #45a049;
            }
            </style>
            """, unsafe_allow_html=True)
            st.button(
                "Start",
                use_container_width=True,
                on_click=lambda: st.session_state.update(started=True)
            )
else: 
    st.title("🌱 Nick")
    st.markdown("---")

    # Chat container for messages
    chat_container = st.container()

    # Input section
    st.markdown("---")

    # Text input with dynamic key for clearing
    user_input = st.text_input(
        "Write your message here...", 
        key=f"text_input_{st.session_state.input_key}"
    )

    # key_input = st_keyup("Press Cmd+Enter to submit", key="cmd_enter_listener")

    # File uploader with dynamic key for clearing
    uploaded_file = st.file_uploader(
        "📎 Image",
        type=["png", "jpg", "jpeg", "gif", "bmp", "webp"],
        key=f"file_uploader_{st.session_state.input_key}",
        help="Image upload"
    )

    # Send button
    col_clear, col_send  = st.columns([8, 1])


    with col_send:
        send_button = st.button("📤 Submit", type="primary", use_container_width=True)

    # Handle message sending
    # if send_button or (key_input and "cmd+enter" in key_input.lower()):
    if send_button:
        # Check if we have either text or image
        has_text = user_input and user_input.strip()
        has_image = uploaded_file is not None
        
        if has_text or has_image:
            # Show processing spinner
            with st.spinner("Processing..."):
                if has_image:
                    # Process image with optional text
                    process_image_and_text(uploaded_file, user_input.strip() if has_text else "")
                elif has_text:
                    # Process text only
                    process_text_only(user_input.strip())
            
            # Clear inputs by incrementing the key (creates new widgets)
            st.session_state.input_key += 1
            st.rerun()
        else:
            st.warning("Por favor escribe un mensaje o sube una imagen.")

    # ---------- Display messages ----------
    with chat_container:
        if st.session_state.messages:
            for message in st.session_state.messages:
                display_message(message)
        else:
            
            info_options = [
                "Hi, I'm Nick! Let's start diagnosing your plants. Describe what problems you see and what changes you've noticed. Write in any language or attach a photo of your plant to get started.",
                "Hi, I'm Nick! Not sure what's happening to your plants? I'll help you treat pests and diseases. Write in any language or attach a photo of your plant to get started.",
                "Hi, I'm Nick! If your plant is being affected by insects, fungi, or slugs, I'll help you treat it. Write in any language or attach a photo of your plant to get started.",
                "Hi, I'm Nick! If your plant is being affected by insects, fungi, or slugs, I'll help you treat it. Write in any language or attach a photo of your plant to get started.",
                "Hi, I'm Nick! If your plant is sick and you don't know how to treat it, I'll help you. Describe its symptoms. Write in any language or attach a photo of your plant to get started."
            ]
            

            st.info(
                random.choice(info_options)
            )

    # ---------- Sidebar ----------
    with st.sidebar:
        st.header("🛠️ Controls")

        if st.button("🔁 Load history", use_container_width=True):
            try:
                st.session_state.messages = []
                st.session_state.message_id = 0
                history = get_history(st.session_state.thread_id)
                for item in history:
                    add_message(
                        item.get("content", ""),
                        "text",
                        "user" if item.get("role") == "user" else "assistant",
                    )
                st.success("Historial recargado")
                st.rerun()
            except Exception as e:
                st.error(f"Error al recargar historial: {e}")

        if st.button("🆕 New Conversation", use_container_width=True):
            st.session_state.thread_id = create_thread()
            st.session_state.messages = []
            st.session_state.message_id = 0
            st.success("Nueva conversación iniciada")
            st.rerun() 