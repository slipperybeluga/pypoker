import gevent
from flask import Flask, render_template, session
from flask_sockets import Sockets
import random
import redis
import uuid
import os
import time
from poker import PlayerClient, \
    ChannelWebSocket, ChannelRedis, MessageQueue, \
    ChannelError, MessageFormatError, MessageTimeout

app = Flask(__name__)
app.config['SECRET_KEY'] = '!!_-pyp0k3r-_!!'
app.debug = True

sockets = Sockets(app)

redis_url = "redis://localhost" if "REDIS_URL" not in os.environ else os.environ["REDIS_URL"]
redis = redis.from_url(redis_url)

# Poker champions: https://en.wikipedia.org/wiki/List_of_World_Series_of_Poker_Main_Event_champions
names = [
    "Johnny Moss",
    "Thomas Preston",
    "Walter Pearson",
    "Brian Roberts",
    "Doyle Brunson",
    "Bobby Baldwin",
    "Hal Fowler",
    "Stu Ungar",
    "Jack Straus",
    "Tom McEvoy",
    "Jack Keller",
    "Bill Smith",
    "Barry Johnston",
    "Johnny Chan",
    "Phil Hellmuth",
    "Mansour Matloubi",
    "Brad Daugherty",
    "Hamid Dastmalchi",
    "Jim Bechtel",
    "Russ Hamilton",
    "Dan Harrington",
    "Huck Seed",
    "Stu Ungar",
    "Scotty Nguyen",
    "Noel Furlong",
    "Chris Ferguson",
    "Carlos Mortensen",
    "Robert Varkonyi",
    "Chris Moneymaker",
    "Greg Raymer",
    "Joe Hachem",
    "Jamie Gold",
    "Jerry Yang",
    "Peter Eastgate",
    "Joe Cada",
    "Jonathan Duhamel",
    "Pius Heinz",
    "Greg Merson",
    "Ryan Riess",
    "Martin Jacobson",
    "Joe McKeehen",
]


@app.route('/')
def hello():
    global names
    if 'player-id' not in session:
        session['player-id'] = str(uuid.uuid4())
        session['player-name'] = random.choice(names)
        session['player-money'] = 1000.00
    return render_template('index.html',
                           id=session['player-id'],
                           name=session['player-name'],
                           money=session['player-money'])


@sockets.route('/poker5')
def poker5(ws):
    client_channel = ChannelWebSocket(ws)

    if 'player-id' not in session:
        client_channel.send_message({"msg_id": "error", "error": "Unrecognized user"})
        client_channel.close()
        return

    session_id = str(uuid.uuid4())

    player_id = session["player-id"]
    player_name = session["player-name"]
    player_money = session["player-money"]

    server_channel = ChannelRedis(
        redis,
        "poker5:player-{}:session-{}:O".format(player_id, session_id),
        "poker5:player-{}:session-{}:I".format(player_id, session_id)
    )

    player = PlayerClient(
        server_channel=server_channel,
        client_channel=client_channel,
        id=player_id,
        name=player_name,
        money=player_money,
        logger=app.logger
    )

    # try:
    app.logger.info("Connecting player {} to a poker5 server...".format(player_id))
    player.connect(MessageQueue(redis), session_id)
    # except (ChannelError, MessageFormatError, MessageTimeout) as e:
    #     app.logger.error("Unable to connect player {} to a poker5 server: {}".format(player_id, e.args[0]))
    #     raise

    def keep_alive():
        last_ping = time.time()
        while not ws.closed:
            # Keep the websocket alive
            gevent.sleep(0.1)
            if time.time() > last_ping + 20:
                # Ping the client every 20 secs to prevent idle connections
                player.send_message_client({"msg_id": "keep_alive"})
                last_ping = time.time()

    try:
        # Keep websocket open
        gevent.spawn(keep_alive)
        player.play()
    except (ChannelError, MessageFormatError, MessageTimeout) as e:
        app.logger.error("Terminating player {} connection: {}".format(player_id, e.args[0]))
    finally:
        app.logger.info("Dropping connection with {}".format(player))
        player.disconnect()
