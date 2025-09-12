from __future__ import annotations

from openai import OpenAI
import os
import time
from typing import List, Dict, Optional

from dotenv import load_dotenv
load_dotenv() 

# Initialize client (reads OPENAI_API_KEY from env if not provided)
openai_client = OpenAI()

# Get your Assistant ID from env
ASSISTANT_ID = os.getenv("ASSISTANT_ID")
if not ASSISTANT_ID:
    raise ValueError("Missing ASSISTANT_ID environment variable.")

# -------- Helpers -------- #

def _extract_text_parts(message) -> str:
    """
    Safely extract text from an OpenAI message object (handles multi-part content).
    """
    parts: List[str] = []
    content = getattr(message, "content", []) or []
    
    for item in content:
        # Handle different content types
        if hasattr(item, 'type'):
            if item.type == "text" and hasattr(item, 'text'):
                text_value = getattr(item.text, 'value', '')
                if text_value:
                    parts.append(text_value)
            elif item.type == "image_file":
                # For image content, we might want to add a placeholder
                parts.append("[Image]")
    
    return "\n".join(parts).strip()

def _poll_run_until_done(thread_id: str, run_id: str, timeout: float = 120.0, poll_interval: float = 1.0):
    """
    Poll the run status until 'completed' or 'failed' or timeout.
    """
    t0 = time.time()
    while True:
        try:
            run = openai_client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run_id)
            status = getattr(run, "status", "")
            
            if status in ("completed", "failed", "cancelled", "expired"):
                return run
            elif status == "requires_action":
                # Handle function calls if needed
                print(f"Run requires action: {status}")
                # You might want to handle tool calls here
                pass
            
            if (time.time() - t0) > timeout:
                raise TimeoutError(f"Run did not complete within {timeout} seconds (status: {status}).")
                
        except Exception as e:
            print(f"Error polling run status: {e}")
            if (time.time() - t0) > timeout:
                raise TimeoutError(f"Run polling failed: {e}")
        
        time.sleep(poll_interval)

# -------- Public API -------- #

def create_thread() -> str:
    """
    Create a new conversation thread and return its ID.
    """
    try:
        thread = openai_client.beta.threads.create()
        return thread.id
    except Exception as e:
        raise RuntimeError(f"Failed to create thread: {e}")

def get_history(thread_id: str) -> List[Dict[str, str]]:
    """
    Retrieve the conversation history for a thread as a list of {role, content} in chronological order.
    """
    try:
        resp = openai_client.beta.threads.messages.list(thread_id=thread_id)
        # API returns reverse-chronological; we normalize to chronological (oldest -> newest)
        items = list(resp.data)[::-1]

        history: List[Dict[str, str]] = []
        for msg in items:
            role = getattr(msg, "role", "assistant")
            text = _extract_text_parts(msg)
            # If no text content (e.g., only attachments), still include an empty string to preserve order.

            # Product links mapping
            product_links = {
                "EcoStatic": " - https://bioreactguatemala.com/product/ecostatic-urbano/",
                "EcoBotanik": " - https://bioreactguatemala.com/product/ecobotanik-1l/",
                "FungiPlus": " - https://bioreactguatemala.com/product/fungiplus-urbano/",
                "ParaFungi": " - https://bioreactguatemala.com/product/parafungi-1l/",
                "DiatoMaster": " - https://bioreactguatemala.com/product/tierra-de-diatomeas-diatomaster-media-libra/"
            }
            # Append product link if mentioned in text
            for product, link in product_links.items():
                if product in text:
                    text += link    
            
            history.append({"role": role, "content": text})
        return history
    except Exception as e:
        print(f"Error getting history: {e}")
        return []

def send_message(
    thread_id: str,
    message: str,
    *,
    assistant_id: Optional[str] = None,
    timeout: float = 120.0,
    poll_interval: float = 1.0
) -> List[str]:
    """
    Send a user message to the given thread, run the assistant, and return the assistant's new replies as a list of strings.
    """
    aid = assistant_id or ASSISTANT_ID

    try:
        # 1) Add user message
        openai_client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=message
        )

        # 2) Create a run for the assistant on this thread
        run = openai_client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=aid
        )

        # 3) Wait until the run finishes
        final_run = _poll_run_until_done(
            thread_id=thread_id, 
            run_id=run.id, 
            timeout=timeout, 
            poll_interval=poll_interval
        )

        if final_run.status != "completed":
            # Basic error surface; you can expand with more detail if needed
            error_msg = f"Run ended with status: {final_run.status}"
            if hasattr(final_run, 'last_error') and final_run.last_error:
                error_msg += f" - Error: {final_run.last_error}"
            raise RuntimeError(error_msg)

        # 4) Fetch latest messages and return ONLY the assistant messages created after this run started
        messages = openai_client.beta.threads.messages.list(thread_id=thread_id)

        assistant_texts: List[str] = []
        for msg in messages.data:
            if getattr(msg, "role", "") == "assistant":
                text = _extract_text_parts(msg)
                if text:
                    assistant_texts.append(text)
            else:
                # Stop when we hit the user message(s) again in reverse order
                break

        # messages.data is reverse-chronological; we collected newest-first, so reverse to oldest-first for readability
        return list(reversed(assistant_texts))
        
    except Exception as e:
        raise RuntimeError(f"Failed to send message: {e}")

def send_image_file(
    thread_id: str,
    text: str,
    file_path: str,
    assistant_id: Optional[str] = None,
    timeout: float = 120.0,
    poll_interval: float = 1.0,
) -> List[str]:
    """
    Uploads an image file, sends it with optional text to the thread, runs the assistant,
    and returns the assistant's replies as a list of strings.
    """
    aid = assistant_id or ASSISTANT_ID
    
    try:
        # Verify file exists
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Get file size for validation
        file_size = os.path.getsize(file_path)
        if file_size > 20 * 1024 * 1024:  # 20MB limit
            raise ValueError(f"File too large: {file_size} bytes (max 20MB)")
        
        # 1) Upload image file
        with open(file_path, "rb") as f:
            file_obj = openai_client.files.create(
                file=f,
                purpose="vision",  # Changed from "assistants" to "vision" for image files
            )

        # 2) Create message content array
        message_content = []
        
        # Add text if provided
        if text and text.strip():
            message_content.append({
                "type": "text",  # Fixed: was "input_text", should be "text"
                "text": text
            })
        
        # Add image
        message_content.append({
            "type": "image_file",  # Fixed: was "input_image", should be "image_file"
            "image_file": {  # Fixed: was "image_url", should be "image_file"
                "file_id": file_obj.id
            }
        })

        # 3) Create the message
        openai_client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=message_content,
        )

        # 4) Run the assistant
        run = openai_client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=aid,
        )

        # 5) Poll until completion
        final_run = _poll_run_until_done(
            thread_id=thread_id,
            run_id=run.id,
            timeout=timeout,
            poll_interval=poll_interval,
        )

        if final_run.status != "completed":
            error_msg = f"Run ended with status: {final_run.status}"
            if hasattr(final_run, 'last_error') and final_run.last_error:
                error_msg += f" - Error: {final_run.last_error}"
            raise RuntimeError(error_msg)

        # 6) Read most recent assistant messages (newest-first) and collect text
        messages = openai_client.beta.threads.messages.list(thread_id=thread_id)

        assistant_texts: List[str] = []
        for msg in messages.data:
            if getattr(msg, "role", "") == "assistant":
                text = _extract_text_parts(msg)
                if text:
                    assistant_texts.append(text)
            else:
                break

        return list(reversed(assistant_texts))
        
    except FileNotFoundError as e:
        raise RuntimeError(f"File error: {e}")
    except ValueError as e:
        raise RuntimeError(f"Validation error: {e}")
    except Exception as e:
        raise RuntimeError(f"Failed to send image: {e}")

def delete_file(file_id: str) -> bool:
    """
    Delete an uploaded file by its ID.
    """
    try:
        openai_client.files.delete(file_id)
        return True
    except Exception as e:
        print(f"Failed to delete file {file_id}: {e}")
        return False

def list_thread_messages(thread_id: str, limit: int = 20) -> List[Dict]:
    """
    List messages in a thread with more detailed information.
    """
    try:
        messages = openai_client.beta.threads.messages.list(
            thread_id=thread_id, 
            limit=limit
        )
        
        result = []
        for msg in reversed(messages.data):  # Chronological order
            result.append({
                "id": msg.id,
                "role": msg.role,
                "content": _extract_text_parts(msg),
                "created_at": msg.created_at,
                "attachments": getattr(msg, 'attachments', [])
            })
        return result
    except Exception as e:
        print(f"Error listing messages: {e}")
        return []