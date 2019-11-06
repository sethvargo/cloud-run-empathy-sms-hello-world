# Copyright 2019 Google, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pyotp

from flask import Flask, jsonify, request
from google.cloud import firestore
from twilio.rest import Client as TwilioClient
from twilio.base.exceptions import TwilioRestException

account_sid = '' # TODO
auth_token  = '' # TODO
from_number = '' # TODO

app = Flask(__name__)
db = firestore.Client()
users_ref = db.collection('users')
twilio_client = TwilioClient(account_sid, auth_token)


# POST /register accepts a JSON payload with a username, name, and phone number.
@app.route("/register", methods=['POST'])
def register():
  # Verify a body was given
  body = request.get_json(force=True, silent=True)
  if not body:
    return jsonify(error='missing or malformed json body'), 400

  # Verify required fields
  username = body.get('username')
  if not username:
    return jsonify(error='missing username field in json body'), 400

  name = body.get('name')
  if not name:
    return jsonify(error='missing name field in json body'), 400

  phone = body.get('phone')
  if not phone:
    return jsonify(error='missing phone field in json body'), 400

  if users_ref.document(username).get().exists:
    return jsonify(error='user already exists'), 400

  parsed_phone = None
  try:
    parsed_phone = twilio_client.lookups.phone_numbers(phone).fetch()
  except TwilioRestException as e:
    return jsonify(error='failed to validate phone number: {}'.format(e)), 400

  users_ref.document(username).set({
    'name': name,
    'phone': parsed_phone.phone_number,
    'totp_secret': pyotp.random_base32(),
  })
  return jsonify(success=True)


# POST /send accepts a JSON payload with a username and sends that user an SMS
# verification with a TOTP code.
@app.route("/send", methods=['POST'])
def send():
  # Verify a body was given
  body = request.get_json(force=True, silent=True)
  if not body:
    return jsonify(error='missing or malformed json body'), 400

  # Verify the body included a "username" field
  username = body.get('username')
  if not username:
    return jsonify(error='missing username field in json body'), 400

  # Lookup the user
  doc = users_ref.document(username).get()
  if not doc.exists:
    return jsonify(error='could not find user'), 400

  name = doc.get('name')
  phone = doc.get('phone')
  totp = pyotp.TOTP(doc.get('totp_secret'))

  # Attempt to send the message
  try:
    message = twilio_client.messages.create(
      to=phone,
      from_=from_number,
      body="Hi {name}, your verification code is: {code}".format(
        name=name,
        code=totp.now()))
  except TwilioRestException as e:
    return jsonify(error=e.msg), 400
  except Exception as e:
    return jsonify(error='failed to send message: {}'.format(e)), 500

  # Success!
  return jsonify(success=True, message_id=message.sid)
