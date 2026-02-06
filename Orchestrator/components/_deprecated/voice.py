"""
Voice Interface Component

Provides speech-to-text and text-to-speech for the Streamlit UI.
Uses browser Web Speech API via JavaScript injection.
"""

import streamlit as st
import streamlit.components.v1 as components


def voice_input_component(key: str = "voice_input") -> str:
    """
    Render a voice input button that uses browser speech recognition.
    
    Returns the transcribed text (stored in session state).
    """
    
    # Initialize session state
    if f"{key}_text" not in st.session_state:
        st.session_state[f"{key}_text"] = ""
    
    # JavaScript for Web Speech API
    voice_js = f"""
    <div id="voice-container" style="margin: 10px 0;">
        <button id="voice-btn" onclick="toggleRecording()" 
                style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                       color: white; border: none; padding: 12px 24px; 
                       border-radius: 25px; cursor: pointer; font-size: 16px;
                       display: flex; align-items: center; gap: 8px;
                       box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
                       transition: all 0.3s ease;">
            <span id="mic-icon">🎤</span>
            <span id="btn-text">Click to Speak</span>
        </button>
        <div id="status" style="margin-top: 8px; font-size: 14px; color: #888;"></div>
        <div id="transcript" style="margin-top: 8px; padding: 10px; 
                                    background: rgba(255,255,255,0.1); 
                                    border-radius: 8px; min-height: 40px;
                                    display: none;"></div>
    </div>
    
    <script>
    let recognition = null;
    let isRecording = false;
    let finalTranscript = '';
    
    // Check for browser support
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    
    if (!SpeechRecognition) {{
        document.getElementById('status').textContent = '⚠️ Speech recognition not supported in this browser. Use Chrome or Edge.';
        document.getElementById('voice-btn').disabled = true;
        document.getElementById('voice-btn').style.opacity = '0.5';
    }} else {{
        recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = 'en-US';
        
        recognition.onstart = function() {{
            isRecording = true;
            document.getElementById('mic-icon').textContent = '🔴';
            document.getElementById('btn-text').textContent = 'Listening...';
            document.getElementById('voice-btn').style.background = 'linear-gradient(135deg, #f5576c 0%, #f093fb 100%)';
            document.getElementById('status').textContent = 'Speak now...';
            document.getElementById('transcript').style.display = 'block';
        }};
        
        recognition.onend = function() {{
            isRecording = false;
            document.getElementById('mic-icon').textContent = '🎤';
            document.getElementById('btn-text').textContent = 'Click to Speak';
            document.getElementById('voice-btn').style.background = 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
            document.getElementById('status').textContent = 'Recording stopped';
            
            // Send transcript to Streamlit
            if (finalTranscript) {{
                // Use Streamlit's setComponentValue if available
                window.parent.postMessage({{
                    type: 'streamlit:setComponentValue',
                    value: finalTranscript
                }}, '*');
                
                // Also try updating via URL parameter trick
                const url = new URL(window.parent.location);
                url.searchParams.set('voice_transcript', encodeURIComponent(finalTranscript));
                // Don't navigate, just log
                console.log('Transcript:', finalTranscript);
            }}
        }};
        
        recognition.onresult = function(event) {{
            let interimTranscript = '';
            
            for (let i = event.resultIndex; i < event.results.length; i++) {{
                const transcript = event.results[i][0].transcript;
                if (event.results[i].isFinal) {{
                    finalTranscript += transcript + ' ';
                }} else {{
                    interimTranscript += transcript;
                }}
            }}
            
            document.getElementById('transcript').innerHTML = 
                '<strong>Final:</strong> ' + finalTranscript + 
                '<br><em style="color: #888;">Interim: ' + interimTranscript + '</em>';
        }};
        
        recognition.onerror = function(event) {{
            document.getElementById('status').textContent = '❌ Error: ' + event.error;
            isRecording = false;
            document.getElementById('mic-icon').textContent = '🎤';
            document.getElementById('btn-text').textContent = 'Click to Speak';
        }};
    }}
    
    function toggleRecording() {{
        if (!recognition) return;
        
        if (isRecording) {{
            recognition.stop();
        }} else {{
            finalTranscript = '';
            document.getElementById('transcript').innerHTML = '';
            recognition.start();
        }}
    }}
    </script>
    """
    
    # Render the component
    components.html(voice_js, height=150)
    
    return st.session_state.get(f"{key}_text", "")


def text_to_speech(text: str, auto_play: bool = True):
    """
    Convert text to speech using browser's speech synthesis.
    
    Args:
        text: The text to speak
        auto_play: Whether to start speaking immediately
    """
    
    # Clean text for speech
    clean_text = text.replace("```", "").replace("#", "").replace("*", "")
    clean_text = clean_text[:1000]  # Limit length
    
    tts_js = f"""
    <script>
    (function() {{
        const text = `{clean_text.replace('`', "'")}`;
        
        if ('speechSynthesis' in window) {{
            // Cancel any ongoing speech
            window.speechSynthesis.cancel();
            
            const utterance = new SpeechSynthesisUtterance(text);
            utterance.rate = 1.0;
            utterance.pitch = 1.0;
            utterance.volume = 1.0;
            
            // Try to use a natural voice
            const voices = window.speechSynthesis.getVoices();
            const preferredVoice = voices.find(v => 
                v.name.includes('Google') || 
                v.name.includes('Samantha') ||
                v.name.includes('Daniel')
            );
            if (preferredVoice) {{
                utterance.voice = preferredVoice;
            }}
            
            {'window.speechSynthesis.speak(utterance);' if auto_play else ''}
        }}
    }})();
    </script>
    """
    
    components.html(tts_js, height=0)


def voice_controls():
    """
    Render voice control buttons (play/pause/stop).
    """
    
    controls_js = """
    <div style="display: flex; gap: 10px; margin: 10px 0;">
        <button onclick="window.speechSynthesis.pause()" 
                style="background: #ffc107; border: none; padding: 8px 16px; border-radius: 5px; cursor: pointer;">
            ⏸️ Pause
        </button>
        <button onclick="window.speechSynthesis.resume()" 
                style="background: #28a745; border: none; padding: 8px 16px; border-radius: 5px; cursor: pointer; color: white;">
            ▶️ Resume
        </button>
        <button onclick="window.speechSynthesis.cancel()" 
                style="background: #dc3545; border: none; padding: 8px 16px; border-radius: 5px; cursor: pointer; color: white;">
            ⏹️ Stop
        </button>
    </div>
    """
    
    components.html(controls_js, height=60)


def render_voice_interface():
    """
    Render the complete voice interface section.
    
    Returns:
        str: The transcribed voice input (if any)
    """
    
    st.markdown("### 🎙️ Voice Interface")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Speech to Text**")
        voice_input_component("main_voice")
        
        # Manual transcript input (fallback)
        manual_text = st.text_area(
            "Or type/paste transcript:",
            height=100,
            placeholder="Voice transcript will appear here, or type manually...",
            key="manual_transcript"
        )
    
    with col2:
        st.markdown("**Text to Speech**")
        st.caption("Agent responses can be read aloud")
        
        if st.checkbox("🔊 Enable voice output", key="tts_enabled"):
            voice_controls()
            st.caption("Responses will be spoken automatically")
    
    return manual_text or st.session_state.get("main_voice_text", "")
