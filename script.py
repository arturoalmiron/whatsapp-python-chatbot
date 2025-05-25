import os
import logging
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import json
from datetime import datetime, timedelta
from collections import defaultdict, deque

load_dotenv()

app = Flask(__name__)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Directory for storing conversations
CONVERSATIONS_DIR = 'conversations'
if not os.path.exists(CONVERSATIONS_DIR):
    os.makedirs(CONVERSATIONS_DIR)
    logging.info(f"Created conversations directory at {CONVERSATIONS_DIR}")

# Ollama configuration (replace Gemini)
OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'gemma3:1b-it-qat')

WASENDER_API_TOKEN = os.getenv('WASENDER_API_TOKEN')
WASENDER_API_URL = "https://wasenderapi.com/api/send-message"

@app.errorhandler(Exception)
def handle_global_exception(e):
    """Global handler for unhandled exceptions."""
    logging.error(f"Unhandled Exception: {e}", exc_info=True)
    return jsonify(status='error', message='An internal server error occurred.'), 500

# --- Load Persona ---
PERSONA_FILE_PATH = 'persona.json'
PERSONA_DESCRIPTION = "Eres un asistente médico virtual para un hospital. Tu trabajo es ayudar a los pacientes a reservar citas médicas de manera amigable y profesional en español." # Default persona for hospital
PERSONA_NAME = "Asistente Médico"
BASE_PROMPT = "Eres un asistente médico virtual amigable y profesional que ayuda a reservar citas en un hospital. Responde siempre en español de manera clara y concisa. Si el usuario no está siguiendo el proceso de reserva de cita, guíalo amablemente hacia ese objetivo."

try:
    with open(PERSONA_FILE_PATH, 'r') as f:
        persona_data = json.load(f)
        custom_description = persona_data.get('description', PERSONA_DESCRIPTION)
        base_prompt = persona_data.get('base_prompt', BASE_PROMPT)
        PERSONA_DESCRIPTION = f"{base_prompt}\n\n{custom_description}"
        PERSONA_NAME = persona_data.get('name', PERSONA_NAME)
    logging.info(f"Successfully loaded persona: {PERSONA_NAME}")
except FileNotFoundError:
    logging.warning(f"Persona file not found at {PERSONA_FILE_PATH}. Using default hospital persona.")
except json.JSONDecodeError:
    logging.error(f"Error decoding JSON from {PERSONA_FILE_PATH}. Using default hospital persona.")
except Exception as e:
    logging.error(f"An unexpected error occurred while loading persona: {e}. Using default hospital persona.")
# --- End Load Persona ---

def load_conversation_history(user_id):
    """Loads conversation history for a given user_id."""
    file_path = os.path.join(CONVERSATIONS_DIR, f"{user_id}.json")
    try:
        with open(file_path, 'r') as f:
            history = json.load(f)
            # Ensure history is a list of dictionaries (pairs of user/assistant messages)
            if isinstance(history, list) and all(isinstance(item, dict) and 'role' in item and 'parts' in item for item in history):
                return history
            else:
                logging.warning(f"Invalid history format in {file_path}. Starting fresh.")
                return []
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        logging.error(f"Error decoding JSON from {file_path}. Starting fresh.")
        return []
    except Exception as e:
        logging.error(f"Unexpected error loading history from {file_path}: {e}")
        return []

def save_conversation_history(user_id, history):
    """Saves conversation history for a given user_id."""
    file_path = os.path.join(CONVERSATIONS_DIR, f"{user_id}.json")
    try:
        with open(file_path, 'w') as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        logging.error(f"Error saving conversation history to {file_path}: {e}")

def split_message(text, max_lines=3, max_chars_per_line=100):
    """Split a long message into smaller chunks for better WhatsApp readability."""
    # First split by existing newlines
    paragraphs = text.split('\\n')
    chunks = []
    current_chunk = []
    current_line_count = 0
    
    for paragraph in paragraphs:
        # Split long paragraphs into smaller lines
        if len(paragraph) > max_chars_per_line:
            words = paragraph.split()
            current_line = []
            current_length = 0
            
            for word in words:
                if current_length + len(word) + 1 <= max_chars_per_line:
                    current_line.append(word)
                    current_length += len(word) + 1
                else:
                    if current_line_count >= max_lines:
                        chunks.append('\n'.join(current_chunk))
                        current_chunk = []
                        current_line_count = 0
                    current_chunk.append(' '.join(current_line))
                    current_line_count += 1
                    current_line = [word]
                    current_length = len(word)
            
            if current_line:
                if current_line_count >= max_lines:
                    chunks.append('\n'.join(current_chunk))
                    current_chunk = []
                    current_line_count = 0
                current_chunk.append(' '.join(current_line))
                current_line_count += 1
        else:
            if current_line_count >= max_lines:
                chunks.append('\n'.join(current_chunk))
                current_chunk = []
                current_line_count = 0
            current_chunk.append(paragraph)
            current_line_count += 1
    
    if current_chunk:
        chunks.append('\n'.join(current_chunk))
    
    return chunks

def get_ollama_response(message_text, conversation_history=None):
    """Generates a response from Ollama using the local API."""
    try:
        # Prepare the prompt with persona and conversation history
        system_prompt = PERSONA_DESCRIPTION
        
        if conversation_history:
            # Format conversation history for Ollama
            history_text = ""
            for item in conversation_history[-6:]:  # Last 6 messages for context
                role = "Usuario" if item['role'] == 'user' else "Asistente"
                content = item['parts'][0] if item['parts'] else ""
                history_text += f"{role}: {content}\n"
            
            full_prompt = f"{system_prompt}\n\nConversación anterior:\n{history_text}\nUsuario: {message_text}\nAsistente:"
        else:
            full_prompt = f"{system_prompt}\n\nUsuario: {message_text}\nAsistente:"

        # Call Ollama API
        ollama_url = f"{OLLAMA_BASE_URL}/api/generate"
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "max_tokens": 200
            }
        }
        
        logging.info(f"Sending prompt to Ollama ({OLLAMA_MODEL}): {message_text[:100]}...")
        
        response = requests.post(ollama_url, json=payload, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        if 'response' in result:
            return result['response'].strip()
        else:
            logging.error(f"Unexpected Ollama response format: {result}")
            return "Lo siento, hay un problema con mi sistema. ¿Puedes intentar de nuevo?"
            
    except requests.exceptions.RequestException as e:
        logging.error(f"Error calling Ollama API: {e}")
        return "No puedo conectarme a mi sistema de IA local. ¿Está Ollama funcionando?"
    except Exception as e:
        logging.error(f"Error processing Ollama response: {e}", exc_info=True)
        return "Hubo un error procesando tu mensaje. Por favor intenta de nuevo."

def send_whatsapp_message(recipient_number, message_content, message_type='text', media_url=None):
    """Sends a message via WaSenderAPI. Supports text and media messages."""
    if not WASENDER_API_TOKEN:
        logging.error("WaSender API token is not set. Please check .env file.")
        return False

    headers = {
        'Authorization': f'Bearer {WASENDER_API_TOKEN}',
        'Content-Type': 'application/json'
    }
    
    # Sanitize recipient_number to remove "@s.whatsapp.net"
    if recipient_number and "@s.whatsapp.net" in recipient_number:
        formatted_recipient_number = recipient_number.split('@')[0]
    else:
        formatted_recipient_number = recipient_number

    payload = {
        'to': formatted_recipient_number
    }

    if message_type == 'text':
        payload['text'] = message_content
    elif message_type == 'image' and media_url:
        payload['imageUrl'] = media_url
        if message_content:
            payload['text'] = message_content 
    elif message_type == 'video' and media_url:
        payload['videoUrl'] = media_url
        if message_content:
            payload['text'] = message_content
    elif message_type == 'audio' and media_url:
        payload['audioUrl'] = media_url
    elif message_type == 'document' and media_url:
        payload['documentUrl'] = media_url
        if message_content:
            payload['text'] = message_content
    else:
        if message_type != 'text':
             logging.error(f"Media URL is required for message type '{message_type}'.")
             return False
        logging.error(f"Unsupported message type or missing content/media_url: {message_type}")
        return False
    
    logging.debug(f"Attempting to send WhatsApp message. Payload: {payload}")

    try:
        response = requests.post(WASENDER_API_URL, headers=headers, json=payload, timeout=20)
        response.raise_for_status()
        logging.info(f"Message sent to {recipient_number}. Response: {response.json()}")
        return True
    except requests.exceptions.RequestException as e:
        status_code = e.response.status_code if e.response is not None else "N/A"
        response_text = e.response.text if e.response is not None else "N/A"
        logging.error(f"Error sending WhatsApp message to {recipient_number} (Status: {status_code}): {e}. Response: {response_text}")
        if status_code == 422:
            logging.error("WaSenderAPI 422 Error: This often means an issue with the payload (e.g., device_id, 'to' format, or message content/URL). Check the payload logged above and WaSenderAPI docs.")
        return False
    except Exception as e:
        logging.error(f"An unexpected error occurred while sending WhatsApp message: {e}")
        return False

# Simulated storage for appointments and user states
appointments = []
user_states = {}

# Rate limiting configuration
RATE_LIMIT_PER_MINUTE = int(os.getenv('RATE_LIMIT_PER_MINUTE', 5))  # Per user
RATE_LIMIT_PER_HOUR = int(os.getenv('RATE_LIMIT_PER_HOUR', 30))   # Per user
RATE_LIMIT_CLEANUP_INTERVAL = 3600  # Clean old data every hour

# Global rate limiting (protects server from being overwhelmed)
GLOBAL_RATE_LIMIT_PER_HOUR = int(os.getenv('GLOBAL_RATE_LIMIT_PER_HOUR', 1000))  # Total requests per hour across all users
GLOBAL_RATE_LIMIT_PER_MINUTE = int(os.getenv('GLOBAL_RATE_LIMIT_PER_MINUTE', 100))  # Total requests per minute across all users

# Rate limiting storage
# Structure: {user_id: {'minute': deque(timestamps), 'hour': deque(timestamps), 'last_cleanup': timestamp}}
rate_limit_data = defaultdict(lambda: {'minute': deque(), 'hour': deque(), 'last_cleanup': datetime.now()})

# Global rate limiting storage
global_rate_limit_data = {'minute': deque(), 'hour': deque()}

def cleanup_old_rate_limit_data():
    """Remove old rate limit entries to prevent memory buildup."""
    current_time = datetime.now()
    users_to_remove = []
    
    # Clean global rate limit data
    one_minute_ago = current_time - timedelta(minutes=1)
    one_hour_ago = current_time - timedelta(hours=1)
    
    while global_rate_limit_data['minute'] and global_rate_limit_data['minute'][0] < one_minute_ago:
        global_rate_limit_data['minute'].popleft()
    
    while global_rate_limit_data['hour'] and global_rate_limit_data['hour'][0] < one_hour_ago:
        global_rate_limit_data['hour'].popleft()
    
    # Clean per-user rate limit data
    for user_id, data in rate_limit_data.items():
        # Clean minute queue (keep only last minute)
        while data['minute'] and data['minute'][0] < one_minute_ago:
            data['minute'].popleft()
        
        # Clean hour queue (keep only last hour)
        while data['hour'] and data['hour'][0] < one_hour_ago:
            data['hour'].popleft()
        
        # Mark user for removal if no recent activity
        if not data['minute'] and not data['hour'] and data['last_cleanup'] < one_hour_ago:
            users_to_remove.append(user_id)
    
    # Remove inactive users
    for user_id in users_to_remove:
        del rate_limit_data[user_id]
    
    logging.info(f"Rate limit cleanup: removed {len(users_to_remove)} inactive users, global data cleaned")

def check_rate_limit(user_id):
    """
    Check if user has exceeded rate limits (both per-user and global).
    Returns (is_allowed, error_message)
    """
    current_time = datetime.now()
    user_data = rate_limit_data[user_id]
    
    # Periodic cleanup
    if current_time - user_data['last_cleanup'] > timedelta(seconds=RATE_LIMIT_CLEANUP_INTERVAL):
        cleanup_old_rate_limit_data()
        user_data['last_cleanup'] = current_time
    
    # Check global rate limits first (protects server)
    one_minute_ago = current_time - timedelta(minutes=1)
    one_hour_ago = current_time - timedelta(hours=1)
    
    # Clean and check global minute limit
    while global_rate_limit_data['minute'] and global_rate_limit_data['minute'][0] < one_minute_ago:
        global_rate_limit_data['minute'].popleft()
    
    if len(global_rate_limit_data['minute']) >= GLOBAL_RATE_LIMIT_PER_MINUTE:
        logging.warning(f"Global rate limit exceeded (per minute): {len(global_rate_limit_data['minute'])} requests")
        return False, f"El sistema está muy ocupado en este momento. Por favor intente de nuevo en unos minutos. (Límite global: {GLOBAL_RATE_LIMIT_PER_MINUTE} solicitudes por minuto)"
    
    # Clean and check global hour limit
    while global_rate_limit_data['hour'] and global_rate_limit_data['hour'][0] < one_hour_ago:
        global_rate_limit_data['hour'].popleft()
    
    if len(global_rate_limit_data['hour']) >= GLOBAL_RATE_LIMIT_PER_HOUR:
        logging.warning(f"Global rate limit exceeded (per hour): {len(global_rate_limit_data['hour'])} requests")
        return False, f"El sistema ha alcanzado su capacidad máxima por hora. Por favor intente más tarde. (Límite global: {GLOBAL_RATE_LIMIT_PER_HOUR} solicitudes por hora)"
    
    # Check per-user rate limits
    while user_data['minute'] and user_data['minute'][0] < one_minute_ago:
        user_data['minute'].popleft()
    
    if len(user_data['minute']) >= RATE_LIMIT_PER_MINUTE:
        logging.warning(f"User rate limit exceeded (per minute) for user {user_id}: {len(user_data['minute'])} messages")
        return False, f"Ha enviado demasiados mensajes muy rápido. Por favor espere un momento antes de continuar. (Límite personal: {RATE_LIMIT_PER_MINUTE} mensajes por minuto)"
    
    while user_data['hour'] and user_data['hour'][0] < one_hour_ago:
        user_data['hour'].popleft()
    
    if len(user_data['hour']) >= RATE_LIMIT_PER_HOUR:
        logging.warning(f"User rate limit exceeded (per hour) for user {user_id}: {len(user_data['hour'])} messages")
        return False, f"Ha alcanzado su límite de mensajes por hora. Por favor intente de nuevo más tarde. (Límite personal: {RATE_LIMIT_PER_HOUR} mensajes por hora)"
    
    # Record this request (both user and global)
    user_data['minute'].append(current_time)
    user_data['hour'].append(current_time)
    global_rate_limit_data['minute'].append(current_time)
    global_rate_limit_data['hour'].append(current_time)
    
    return True, ""

def get_rate_limit_status(user_id):
    """Get current rate limit status for a user (for debugging/monitoring)."""
    if user_id not in rate_limit_data:
        return {"minute_count": 0, "hour_count": 0}
    
    current_time = datetime.now()
    user_data = rate_limit_data[user_id]
    
    # Count recent messages
    one_minute_ago = current_time - timedelta(minutes=1)
    one_hour_ago = current_time - timedelta(hours=1)
    
    minute_count = sum(1 for ts in user_data['minute'] if ts >= one_minute_ago)
    hour_count = sum(1 for ts in user_data['hour'] if ts >= one_hour_ago)
    
    return {
        "minute_count": minute_count,
        "hour_count": hour_count,
        "minute_limit": RATE_LIMIT_PER_MINUTE,
        "hour_limit": RATE_LIMIT_PER_HOUR
    }

# Spanish prompts for each step
prompts = [
    "¿Cuál es su nombre completo?",
    "¿Cuál es la fecha y hora de la cita que desea reservar? (Ejemplo: 25/05/2025 14:30)",
    "¿Con qué departamento o doctor desea la cita?",
    "Por favor, proporcione su número de identificación (ID)."
]

def validate_appointment_date(date_string):
    """Validate if the appointment date is in the future."""
    try:
        # Try different date formats
        for fmt in ["%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M", "%Y-%m-%d %H:%M"]:
            try:
                appointment_date = datetime.strptime(date_string, fmt)
                break
            except ValueError:
                continue
        else:
            return False, "Formato de fecha inválido. Use: DD/MM/YYYY HH:MM"
        
        # Check if date is in the future
        if appointment_date <= datetime.now():
            return False, "La fecha debe ser en el futuro."
        
        # Check if it's within business hours (8 AM to 6 PM)
        if appointment_date.hour < 8 or appointment_date.hour >= 18:
            return False, "Las citas solo están disponibles de 8:00 AM a 6:00 PM."
        
        # Check if it's a weekday
        if appointment_date.weekday() >= 5:  # Saturday = 5, Sunday = 6
            return False, "Las citas solo están disponibles de lunes a viernes."
        
        return True, "Fecha válida"
    except Exception as e:
        return False, "Error validando la fecha."

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No JSON data received'}), 400
            
        user_id = data.get('from')  # WhatsApp number
        message = data.get('body', '').strip()

        # Check rate limits first
        is_allowed, rate_limit_error = check_rate_limit(user_id)
        if not is_allowed:
            logging.warning(f"Rate limit exceeded for user {user_id}. Message: {message[:50]}")
            return jsonify({'reply': rate_limit_error})

        # Initialize state if new user
        if user_id not in user_states:
            user_states[user_id] = {'step': 0, 'data': {}}
            return jsonify({'reply': prompts[0]})

        state = user_states[user_id]
        step = state['step']

        # Save the user's answer
        if step == 0:
            state['data']['nombre'] = message
        elif step == 1:
            # Validate date before saving
            is_valid, error_message = validate_appointment_date(message)
            if not is_valid:
                return jsonify({'reply': f"{error_message} Por favor, intente de nuevo."})
            state['data']['fecha_hora'] = message
        elif step == 2:
            state['data']['departamento_doctor'] = message
        elif step == 3:
            state['data']['id'] = message
            # Placeholder for future insurance check
            # When you have database access, check insurance here:
            # has_insurance = check_insurance(state['data']['id'])
            # if not has_insurance:
            #     return jsonify({'reply': 'Lo siento, no se encontró seguro para este ID. ¿Desea continuar sin seguro?'})

        # Move to next step or finish
        if step < 3:
            state['step'] += 1
            return jsonify({'reply': prompts[state['step']]})
        else:
            # Save appointment
            appointments.append(state['data'])
            confirmation = (
                f"¡Gracias! Su cita ha sido reservada:\n"
                f"Nombre: {state['data']['nombre']}\n"
                f"Fecha y hora: {state['data']['fecha_hora']}\n"
                f"Departamento/Doctor: {state['data']['departamento_doctor']}\n"
                f"ID: {state['data']['id']}\n"
                "Si necesita cambiar o cancelar la cita, por favor responda a este mensaje."
            )
            # Reset user state
            del user_states[user_id]
            return jsonify({'reply': confirmation})
    except Exception as e:
        logging.error(f"Error in webhook: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/admin/status', methods=['GET'])
def admin_status():
    """Admin endpoint to check system status and rate limits."""
    try:
        current_time = datetime.now()
        
        # Get rate limit statistics
        active_users = len(rate_limit_data)
        total_appointments = len(appointments)
        active_conversations = len(user_states)
        
        # Calculate global usage
        one_minute_ago = current_time - timedelta(minutes=1)
        one_hour_ago = current_time - timedelta(hours=1)
        
        global_minute_count = sum(1 for ts in global_rate_limit_data['minute'] if ts >= one_minute_ago)
        global_hour_count = sum(1 for ts in global_rate_limit_data['hour'] if ts >= one_hour_ago)
        
        # Calculate rate limit usage
        rate_limit_stats = {}
        for user_id in list(rate_limit_data.keys())[:10]:  # Show top 10 for brevity
            stats = get_rate_limit_status(user_id)
            if stats['minute_count'] > 0 or stats['hour_count'] > 0:
                rate_limit_stats[user_id] = stats
        
        return jsonify({
            'status': 'healthy',
            'timestamp': current_time.isoformat(),
            'statistics': {
                'active_users_with_rate_data': active_users,
                'total_appointments': total_appointments,
                'active_conversations': active_conversations,
                'global_usage': {
                    'requests_last_minute': global_minute_count,
                    'requests_last_hour': global_hour_count,
                    'minute_limit': GLOBAL_RATE_LIMIT_PER_MINUTE,
                    'hour_limit': GLOBAL_RATE_LIMIT_PER_HOUR,
                    'minute_usage_percent': round((global_minute_count / GLOBAL_RATE_LIMIT_PER_MINUTE) * 100, 1),
                    'hour_usage_percent': round((global_hour_count / GLOBAL_RATE_LIMIT_PER_HOUR) * 100, 1)
                },
                'per_user_limits': {
                    'per_minute': RATE_LIMIT_PER_MINUTE,
                    'per_hour': RATE_LIMIT_PER_HOUR
                }
            },
            'recent_rate_limit_usage': rate_limit_stats,
            'ollama_status': 'configured' if os.getenv('OLLAMA_BASE_URL') else 'not_configured'
        })
    except Exception as e:
        logging.error(f"Error in admin status: {e}")
        return jsonify({'error': 'Unable to get status'}), 500

@app.route('/admin/rate-limits/<user_id>', methods=['GET'])
def admin_user_rate_limit(user_id):
    """Get rate limit status for a specific user."""
    try:
        stats = get_rate_limit_status(user_id)
        return jsonify({
            'user_id': user_id,
            'rate_limit_status': stats,
            'has_active_conversation': user_id in user_states
        })
    except Exception as e:
        logging.error(f"Error getting rate limit for user {user_id}: {e}")
        return jsonify({'error': 'Unable to get user rate limit'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)
