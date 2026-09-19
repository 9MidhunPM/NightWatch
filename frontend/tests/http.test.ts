import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readJson} from '../lib/http';
import {checkReadiness} from '../lib/readiness';

test('readJson returns structured JSON responses',async()=>{
 const response=Response.json({projects:3});
 assert.deepEqual(await readJson<{projects:number}>(response),{projects:3});
});

test('readJson surfaces API messages for JSON errors',async()=>{
 const response=Response.json({message:'Backend unavailable'},{status:502});
 await assert.rejects(()=>readJson(response),/Backend unavailable/);
});

test('readJson replaces HTML responses with a useful error',async()=>{
 const response=new Response('<!DOCTYPE html><title>Bad Gateway</title>',{status:502,headers:{'Content-Type':'text/html'}});
 await assert.rejects(()=>readJson(response),/temporarily unavailable/);
});

test('readiness reports the private backend connection',async()=>{
 const ready=await checkReadiness(async()=>Response.json({status:'ok'}));
 assert.deepEqual(ready,{status:'ok',frontend:'ok',backend:'ok'});
 const unavailable=await checkReadiness(async()=>new Response('<!DOCTYPE html>',{status:502,headers:{'Content-Type':'text/html'}}));
 assert.deepEqual(unavailable,{status:'degraded',frontend:'ok',backend:'unavailable'});
});
