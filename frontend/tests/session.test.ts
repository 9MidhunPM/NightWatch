import {test} from 'node:test';import assert from 'node:assert/strict';import {issueSession,validSession} from '../lib/session';
const secret='a'.repeat(40);
test('sessions reject tampering, expiry and missing secrets',()=>{const now=Date.now(),session=issueSession(secret,now);assert.ok(validSession(session,secret,now));assert.ok(!validSession(session+'x',secret,now));assert.ok(!validSession(session,secret,now+9*3600000));assert.ok(!validSession(session,undefined,now));assert.ok(!validSession(session,'b'.repeat(40),now));});
