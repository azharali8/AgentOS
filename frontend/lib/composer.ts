export interface Attachment {name:string;content:string}
export const ACCEPTED_CONTEXT = '.txt,.md,.py,.js,.ts,.tsx,.jsx,.json,.csv,.yaml,.yml,.html,.css';
export async function readAttachment(file:File):Promise<Attachment> {
 const ext='.'+file.name.split('.').pop()?.toLowerCase();
 if(!ACCEPTED_CONTEXT.split(',').includes(ext)||file.name.startsWith('.')||/[\\/:]/.test(file.name))throw new Error('Choose a text or source file. PDF and binary files are not supported.');
 if(file.size>32768)throw new Error('Each file must be 32 KB or smaller.');
 const content=new TextDecoder('utf-8',{fatal:true}).decode(await file.arrayBuffer());
 if(content.includes('\0'))throw new Error('Binary files are not supported.');
 return {name:file.name,content};
}
export function shouldSubmit(key:string,shift:boolean,composing:boolean) {return key==='Enter'&&!shift&&!composing;}
