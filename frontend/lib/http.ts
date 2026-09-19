type ErrorBody={message?:unknown;detail?:unknown};

export async function readJson<T>(response:Response):Promise<T>{
 const contentType=response.headers.get('content-type')||'';
 const text=await response.text();
 if(!contentType.toLowerCase().includes('application/json')){
  throw new Error(response.status>=500?'The service is temporarily unavailable. Try again shortly.':'The server returned an unexpected response.');
 }
 let data:unknown;
 try{data=text?JSON.parse(text):{};}catch{throw new Error('The server returned an invalid response.');}
 if(!response.ok){const body=data as ErrorBody;const message=typeof body.message==='string'?body.message:typeof body.detail==='string'?body.detail:'Request failed';throw new Error(message);}
 return data as T;
}
