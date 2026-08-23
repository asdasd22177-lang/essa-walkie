from gevent import monkey
monkey.patch_all()

import os
from flask import Flask, render_template_string, request
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
app.config['SECRET_KEY'] = 'essa_walkie_admin_2026'

# ترك async_mode ليتعرف عليه النظام تلقائياً وبشكل آمن
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

ADMIN_CODE = "1234"
pending_users = {}   # {socket_id: {'name': name, 'room': room}}
approved_users = {}  # {socket_id: {'name': name, 'room': room, 'is_admin': bool}}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Essa Walkie Admin 📻</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Segoe UI', Tahoma, sans-serif; background-color: #0f172a; color: #f8fafc; text-align: center; padding: 15px; }
        .container { max-width: 480px; margin: 0 auto; background: #1e293b; border-radius: 20px; padding: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
        h1 { color: #38bdf8; font-size: 22px; margin-bottom: 15px; }
        .card { background: #0f172a; border-radius: 12px; padding: 15px; margin-bottom: 15px; border: 1px solid #334155; }
        input { width: 100%; padding: 10px; border-radius: 8px; border: 1px solid #475569; background: #1e293b; color: white; text-align: center; font-size: 15px; margin-bottom: 8px; }
        .btn { background: #0284c7; color: white; width: 100%; padding: 10px; border-radius: 8px; border: none; font-size: 15px; font-weight: bold; cursor: pointer; }
        .talk-btn { width: 150px; height: 150px; border-radius: 50%; background: linear-gradient(145deg, #22c55e, #16a34a); color: white; font-size: 18px; font-weight: bold; border: none; box-shadow: 0 0 20px rgba(34, 197, 94, 0.4); cursor: pointer; user-select: none; margin: 15px auto; display: flex; align-items: center; justify-content: center; touch-action: manipulation; }
        .talk-btn:active, .talk-btn.active { transform: scale(0.95); background: linear-gradient(145deg, #ef4444, #dc2626); box-shadow: 0 0 20px rgba(239, 68, 68, 0.6); }
        .user-item { display: flex; justify-content: space-between; align-items: center; background: #1e293b; padding: 8px 12px; border-radius: 6px; margin-bottom: 5px; font-size: 14px; }
        .btn-kick { background: #dc2626; color: white; border: none; padding: 4px 8px; border-radius: 4px; cursor: pointer; }
        .btn-approve { background: #16a34a; color: white; border: none; padding: 4px 8px; border-radius: 4px; cursor: pointer; margin-left: 5px; }
        .status-badge { font-size: 12px; margin-bottom: 10px; color: #38bdf8; }
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
            <input type="password" id="adminCode" placeholder="رمز الأدمن (اختياري للأدمن فقط)">
            <button class="btn" onclick="requestJoin()">طلب الانضمام</button>
        </div>

        <div id="waitSection" class="card hidden">
            <p style="color: #eab308;">⏳ بانتظار موافقة الأدمن على دخولك...</p>
        </div>

        <div id="appSection" class="card hidden">
            <p style="font-size: 14px; color: #94a3b8;">الغرفة: <span id="currentRoom" style="color:#38bdf8;"></span> | المستخدم: <span id="currentUser"></span></p>
            <p id="statusText" style="margin-top:10px;">اضغط وتحدث ليسمعك الجميع ✅</p>
            
            <button class="talk-btn" id="talkBtn" 
                    onmousedown="startSpeaking(event)" onmouseup="stopSpeaking(event)" onmouseleave="stopSpeaking(event)"
                    ontouchstart="startSpeaking(event)" ontouchend="stopSpeaking(event)" ontouchcancel="stopSpeaking(event)">
                تحدث الآن 🎙️
            </button>

            <div id="adminPanel" class="hidden" style="margin-top:15px; border-top:1px solid #334155; padding-top:10px;">
                <h3 style="color:#ef4444; font-size:15px; margin-bottom:8px;">🛠️ لوحة تحكم الأدمن</h3>
                <div id="pendingList"></div>
                <div id="usersList"></div>
            </div>
        </div>
    </div>

    <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
    <script>
        const socket = io();
        let currentRoom = "", myName = "", isAdmin = false;
        let mediaRecorder, audioChunks = [], isSpeaking = false;

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
            if (!socket.connected) return alert("جاري الاتصال بالسيرفر، يرجى الانتظار ثوانٍ ثم المحاولة.");
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
        });

        socket.on('join_rejected', () => { alert("❌ تم رفض طلبك."); location.reload(); });
        socket.on('kicked', () => { alert("⚠️ تم إخراجك من الغرفة."); location.reload(); });

        function initMicrophone() {
            navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
                mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
                mediaRecorder.ondataavailable = e => { if (e.data.size > 0) audioChunks.push(e.data); };
                mediaRecorder.onstop = () => {
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
            if(isSpeaking || !mediaRecorder) return;
            isSpeaking = true;
            document.getElementById('talkBtn').classList.add('active');
            audioChunks = [];
            mediaRecorder.start();
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
            audio.play().catch(e => console.log("خطأ في تشغيل الصوت", e));
        });

        socket.on('update_admin_lists', data => {
            if(!isAdmin) return;
            let pHTML = "<b>طلبات الدخول:</b><br>";
            data.pending.forEach(u => {
                pHTML += `<div class="user-item"><span>${u.name}</span><div>
                    <button class="btn-approve" onclick="approveUser('${u.id}')">قبول</button>
                    <button class="btn-kick" onclick="rejectUser('${u.id}')">رفض</button>
                </div></div>`;
            });
            document.getElementById('pendingList').innerHTML = pHTML;

            let uHTML = "<br><b>المتواجدون بالغرفة:</b><br>";
            data.approved.forEach(u => {
                uHTML += `<div class="user-item"><span>${u.name}</span>
                    ${!u.is_admin ? `<button class="btn-kick" onclick="kickUser('${u.id}')">طرد</button>` : ''}
                </div>`;
            });
            document.getElementById('usersList').innerHTML = uHTML;
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
    
    broadcast_admin_lists(room)

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
        broadcast_admin_lists(room)

    elif action == 'reject' and target_id in pending_users:
        room = pending_users[target_id]['room']
        pending_users.pop(target_id)
        socketio.emit('join_rejected', to=target_id)
        broadcast_admin_lists(room)

    elif action == 'kick' and target_id in approved_users:
        room = approved_users[target_id]['room']
        approved_users.pop(target_id)
        socketio.emit('kicked', to=target_id)
        leave_room(room, sid=target_id)
        broadcast_admin_lists(room)

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    room = None
    
    if sid in pending_users:
        room = pending_users.pop(sid)['room']
    elif sid in approved_users:
        room = approved_users.pop(sid)['room']
        
    if room:
        broadcast_admin_lists(room)

@socketio.on('voice_data')
def handle_voice(data):
    if request.sid in approved_users:
        emit('receive_voice', data, room=data['room'], include_self=False)

def broadcast_admin_lists(room):
    pending = [{'id': k, 'name': v['name']} for k, v in pending_users.items() if v['room'] == room]
    approved = [{'id': k, 'name': v['name'], 'is_admin': v['is_admin']} for k, v in approved_users.items() if v['room'] == room]
    
    for sid, u in approved_users.items():
        if u['room'] == room and u['is_admin']:
            emit('update_admin_lists', {'pending': pending, 'approved': approved}, to=sid)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port)
