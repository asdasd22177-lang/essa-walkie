from gevent import monkey
monkey.patch_all()

import os
from flask import Flask, render_template_string, request
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
app.config['SECRET_KEY'] = 'essa_walkie_admin_2026'

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

ADMIN_CODE = "1234"
pending_users = {}   
approved_users = {}  
speaking_state = {}  

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Essa Walkie Talkie 📻</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Segoe UI', Tahoma, sans-serif; background-color: #0f172a; color: #f8fafc; text-align: center; padding: 10px; }
        .container { max-width: 480px; margin: 0 auto; background: #1e293b; border-radius: 20px; padding: 15px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
        h1 { color: #38bdf8; font-size: 20px; margin-bottom: 10px; }
        .card { background: #0f172a; border-radius: 12px; padding: 12px; margin-bottom: 10px; border: 1px solid #334155; }
        input, textarea { width: 100%; padding: 8px; border-radius: 8px; border: 1px solid #475569; background: #1e293b; color: white; text-align: center; font-size: 14px; margin-bottom: 6px; }
        .btn { background: #0284c7; color: white; width: 100%; padding: 8px; border-radius: 8px; border: none; font-size: 14px; font-weight: bold; cursor: pointer; }
        .talk-btn { width: 130px; height: 130px; border-radius: 50%; background: linear-gradient(145deg, #22c55e, #16a34a); color: white; font-size: 16px; font-weight: bold; border: none; box-shadow: 0 0 15px rgba(34, 197, 94, 0.4); cursor: pointer; user-select: none; margin: 10px auto; display: flex; align-items: center; justify-content: center; touch-action: manipulation; }
        .talk-btn:active, .talk-btn.active { transform: scale(0.95); background: linear-gradient(145deg, #ef4444, #dc2626); box-shadow: 0 0 15px rgba(239, 68, 68, 0.6); }
        .user-item { display: flex; justify-content: space-between; align-items: center; background: #1e293b; padding: 6px 10px; border-radius: 6px; margin-bottom: 4px; font-size: 13px; border-right: 3px solid #64748b; }
        .user-item.speaking { border-right-color: #22c55e; background: #064e3b; }
        .btn-kick { background: #dc2626; color: white; border: none; padding: 3px 6px; border-radius: 4px; cursor: pointer; font-size: 12px; }
        .btn-approve { background: #16a34a; color: white; border: none; padding: 3px 6px; border-radius: 4px; cursor: pointer; margin-left: 4px; font-size: 12px; }
        .mute-btn { background: #eab308; color: #0f172a; border: none; padding: 6px 12px; border-radius: 6px; font-weight: bold; cursor: pointer; margin-bottom: 8px; font-size: 13px; width: 100%; }
        .mute-btn.muted { background: #dc2626; color: white; }
        .status-badge { font-size: 11px; margin-bottom: 8px; color: #38bdf8; }
        .chat-box { height: 100px; overflow-y: auto; background: #0f172a; border: 1px solid #334155; border-radius: 6px; padding: 6px; text-align: right; font-size: 12px; margin-bottom: 6px; }
        .chat-msg { margin-bottom: 4px; border-bottom: 1px solid #1e293b; padding-bottom: 2px; }
        .chat-input-row { display: flex; gap: 5px; }
        .hidden { display: none; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📻 Essa Walkie Talkie</h1>
        <div id="connStatus" class="status-badge">جاري الاتصال بالسيرفر...</div>
        
        <div id="loginSection" class="card">
            <input type="text" id="username" placeholder="اسمك">
            <input type="text" id="roomInput" placeholder="رقم الغرفة (مثال: 101)" value="101">
            <input type="password" id="adminCode" placeholder="رمز الأدمن (اختياري)">
            <button class="btn" onclick="requestJoin()">طلب الانضمام</button>
        </div>

        <div id="waitSection" class="card hidden">
            <p style="color: #eab308; font-size: 14px;">⏳ بانتظار موافقة الأدمن على دخولك...</p>
        </div>

        <div id="appSection" class="card hidden">
            <p style="font-size: 13px; color: #94a3b8;">الغرفة: <span id="currentRoom" style="color:#38bdf8;"></span> | المستخدم: <span id="currentUser"></span></p>
            
            <button id="muteBtn" class="mute-btn" onclick="toggleMute()">🎙️ الميكروفون مفعل</button>
            
            <button class="talk-btn" id="talkBtn" 
                    onmousedown="startSpeaking(event)" onmouseup="stopSpeaking(event)" onmouseleave="stopSpeaking(event)"
                    ontouchstart="startSpeaking(event)" ontouchend="stopSpeaking(event)" ontouchcancel="stopSpeaking(event)">
                تحدث الآن 🎙️
            </button>

            <div style="margin-top:8px; text-align:right;">
                <b style="font-size: 13px; color: #38bdf8;">👥 المتواجدون في الغرفة:</b>
                <div id="publicUsersList" style="max-height: 90px; overflow-y: auto; margin-top: 4px;"></div>
            </div>

            <div style="margin-top: 10px; text-align: right;">
                <b style="font-size: 13px; color: #38bdf8;">💬 الدردشة النصية:</b>
                <div id="chatBox" class="chat-box"></div>
                <div class="chat-input-row">
                    <input type="text" id="chatInput" placeholder="اكتب رسالة..." style="margin-bottom:0;" onkeypress="checkEnter(event)">
                    <button class="btn" style="width: 70px; padding: 6px;" onclick="sendChatMessage()">إرسال</button>
                </div>
            </div>

            <div id="adminPanel" class="hidden" style="margin-top:10px; border-top:1px solid #334155; padding-top:8px; text-align:right;">
                <h3 style="color:#ef4444; font-size:14px; margin-bottom:6px;">🛠️ لوحة تحكم الأدمن (طلبات الانضمام)</h3>
                <div id="pendingList"></div>
            </div>
        </div>
    </div>

    <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
    <script>
        const socket = io();
        let currentRoom = "", myName = "", isAdmin = false;
        let mediaRecorder, audioChunks = [], isSpeaking = false, isMuted = false;

        function playBeep(freq = 440, duration = 100) {
            try {
                const ctx = new (window.AudioContext || window.webkitAudioContext)();
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = "sine";
                osc.frequency.value = freq;
                gain.gain.setValueAtTime(0.1, ctx.currentTime);
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start();
                setTimeout(() => { osc.stop(); ctx.close(); }, duration);
            } catch(e) {}
        }

        socket.on('connect', () => {
            document.getElementById('connStatus').innerText = "متصل بالسيرفر ✅";
            document.getElementById('connStatus').style.color = "#22c55e";
        });

        socket.on('connect_error', () => {
            document.getElementById('connStatus').innerText = "جاري إعادة الاتصال... ⚠️";
            document.getElementById('connStatus').style.color = "#eab308";
        });

        socket.on('disconnect', () => {
            document.getElementById('connStatus').innerText = "تم قطع الاتصال ❌";
            document.getElementById('connStatus').style.color = "#ef4444";
        });

        function requestJoin() {
            if (!socket.connected) return alert("جاري الاتصال بالسيرفر، يرجى الانتظار ثوانٍ.");
            myName = document.getElementById('username').value.trim();
            currentRoom = document.getElementById('roomInput').value.trim();
            const adminCode = document.getElementById('adminCode').value.trim();

            if(!myName || !currentRoom) return alert("يرجى كتابة الاسم ورقم الغرفة");

            document.getElementById('loginSection').classList.add('hidden');
            document.getElementById('waitSection').classList.remove('hidden');
            socket.emit('request_join', { name: myName, room: currentRoom, admin_code: adminCode });
        }

        socket.on('join_approved', data => {
            isAdmin = data.is_admin;
            document.getElementById('waitSection').classList.add('hidden');
            document.getElementById('appSection').classList.remove('hidden');
            document.getElementById('currentRoom').innerText = currentRoom;
            document.getElementById('currentUser').innerText = myName + (isAdmin ? " (أدمن)" : "");
            if(isAdmin) document.getElementById('adminPanel').classList.remove('hidden');
            initMicrophone();
            playBeep(600, 150);
        });

        socket.on('join_rejected', () => { alert("❌ تم رفض طلبك."); location.reload(); });
        socket.on('kicked', () => { alert("⚠️ تم إخراجك من الغرفة."); location.reload(); });

        function toggleMute() {
            isMuted = !isMuted;
            const btn = document.getElementById('muteBtn');
            if(isMuted) {
                btn.innerText = "🔇 الميكروفون مكتوم";
                btn.classList.add('muted');
            } else {
                btn.innerText = "🎙️ الميكروفون مفعل";
                btn.classList.remove('muted');
            }
        }

        function initMicrophone() {
            navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
                // إعدادات محسنة لضغط الصوت وتخفيف حجمه ليكون أسرع بكثير
                mediaRecorder = new MediaRecorder(stream, { 
                    mimeType: 'audio/webm;codecs=opus',
                    audioBitsPerSecond: 24000 
                });
                mediaRecorder.ondataavailable = e => { if (e.data.size > 0) audioChunks.push(e.data); };
                mediaRecorder.onstop = () => {
                    socket.emit('set_speaking', { room: currentRoom, speaking: false });
                    const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                    audioChunks = [];
                    audioBlob.arrayBuffer().then(buffer => {
                        socket.emit('voice_data', { room: currentRoom, audio: buffer });
                    });
                };
            }).catch(err => alert("يرجى إعطاء إذن الميكروفون للعمل"));
        }

        function startSpeaking(e) {
            if(e) e.preventDefault();
            if(isMuted || isSpeaking || !mediaRecorder) return;
            isSpeaking = true;
            document.getElementById('talkBtn').classList.add('active');
            socket.emit('set_speaking', { room: currentRoom, speaking: true });
            audioChunks = [];
            mediaRecorder.start();
            playBeep(800, 50);
        }

        function stopSpeaking(e) {
            if(e) e.preventDefault();
            if(!isSpeaking || !mediaRecorder) return;
            isSpeaking = false;
            document.getElementById('talkBtn').classList.remove('active');
            mediaRecorder.stop();
        }

        socket.on('receive_voice', data => {
            const blob = new Blob([data.audio], { type: 'audio/webm' });
            const url = URL.createObjectURL(blob);
            const audio = new Audio(url);
            audio.play().catch(e => console.log(e));
        });

        function checkEnter(e) { if(e.key === 'Enter') sendChatMessage(); }
        function sendChatMessage() {
            const input = document.getElementById('chatInput');
            const msg = input.value.trim();
            if(!msg) return;
            socket.emit('send_chat', { room: currentRoom, name: myName, message: msg });
            input.value = '';
        }

        socket.on('receive_chat', data => {
            const box = document.getElementById('chatBox');
            box.innerHTML += `<div class="chat-msg"><b>${data.name}:</b> ${data.message}</div>`;
            box.scrollTop = box.scrollHeight;
        });

        socket.on('update_room_data', data => {
            let pubHTML = "";
            data.approved.forEach(u => {
                const isSpk = data.speaking_users && data.speaking_users[u.id];
                pubHTML += `<div class="user-item ${isSpk ? 'speaking' : ''}">
                    <span>${u.name} ${isSpk ? '🎙️ (يتحدث الآن...)' : ''}</span>
                    ${isAdmin && !u.is_admin ? `<button class="btn-kick" onclick="kickUser('${u.id}')">طرد</button>` : ''}
                </div>`;
            });
            document.getElementById('publicUsersList').innerHTML = pubHTML;

            if(isAdmin) {
                let pHTML = "";
                if(data.pending.length === 0) {
                    pHTML = "<span style='color:#94a3b8; font-size:12px;'>لا توجد طلبات معلقة</span>";
                } else {
                    data.pending.forEach(u => {
                        pHTML += `<div class="user-item"><span>${u.name}</span><div>
                            <button class="btn-approve" onclick="approveUser('${u.id}')">قبول</button>
                            <button class="btn-kick" onclick="rejectUser('${u.id}')">رفض</button>
                        </div></div>`;
                    });
                }
                document.getElementById('pendingList').innerHTML = pHTML;
            }
        });

        function approveUser(id) { socket.emit('admin_action', { action: 'approve', target_id: id }); }
        function rejectUser(id) { socket.emit('admin_action', { action: 'reject', target_id: id }); }
        function kickUser(id) { socket.emit('admin_action', { action: 'kick', target_id: id }); }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@socketio.on('request_join')
def handle_request(data):
    sid = request.sid
    is_admin = (data.get('admin_code') == ADMIN_CODE)
    room = data['room']
    
    if is_admin:
        approved_users[sid] = {'name': data['name'], 'room': room, 'is_admin': True}
        join_room(room)
        emit('join_approved', {'is_admin': True})
    else:
        pending_users[sid] = {'name': data['name'], 'room': room}
    
    broadcast_room_data(room)

@socketio.on('set_speaking')
def handle_set_speaking(data):
    room = data['room']
    sid = request.sid
    if room not in speaking_state:
        speaking_state[room] = {}
    speaking_state[room][sid] = data['speaking']
    broadcast_room_data(room)

@socketio.on('admin_action')
def handle_admin_action(data):
    sid = request.sid
    if sid not in approved_users or not approved_users[sid]['is_admin']:
        return

    action = data['action']
    target_id = data['target_id']

    if action == 'approve' and target_id in pending_users:
        u_info = pending_users.pop(target_id)
        room = u_info['room']
        approved_users[target_id] = {'name': u_info['name'], 'room': room, 'is_admin': False}
        socketio.emit('join_approved', {'is_admin': False}, to=target_id)
        join_room(room, sid=target_id)
        broadcast_room_data(room)

    elif action == 'reject' and target_id in pending_users:
        room = pending_users[target_id]['room']
        pending_users.pop(target_id)
        socketio.emit('join_rejected', to=target_id)
        broadcast_room_data(room)

    elif action == 'kick' and target_id in approved_users:
        room = approved_users[target_id]['room']
        approved_users.pop(target_id)
        if target_id in speaking_state.get(room, {}):
            speaking_state[room].pop(target_id)
        socketio.emit('kicked', to=target_id)
        leave_room(room, sid=target_id)
        broadcast_room_data(room)

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    room = None
    if sid in pending_users:
        room = pending_users.pop(sid)['room']
    elif sid in approved_users:
        room = approved_users.pop(sid)['room']
        for r in speaking_state:
            if sid in speaking_state[r]:
                speaking_state[r].pop(sid)
    if room:
        broadcast_room_data(room)

@socketio.on('voice_data')
def handle_voice(data):
    if request.sid in approved_users:
        emit('receive_voice', data, room=data['room'], include_self=False)

@socketio.on('send_chat')
def handle_chat(data):
    room = data.get('room')
    if request.sid in approved_users and room:
        emit('receive_chat', {'name': data['name'], 'message': data['message']}, room=room)

def broadcast_room_data(room):
    pending = [{'id': k, 'name': v['name']} for k, v in pending_users.items() if v['room'] == room]
    approved = [{'id': k, 'name': v['name'], 'is_admin': v['is_admin']} for k, v in approved_users.items() if v['room'] == room]
    spk = speaking_state.get(room, {})
    socketio.emit('update_room_data', {'pending': pending, 'approved': approved, 'speaking_users': spk}, room=room)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port)
