export type Theme = 'light'|'dark'|'system';
export function resolvedTheme(theme:Theme,systemDark:boolean) { return theme==='system'?(systemDark?'dark':'light'):theme; }
export function savedTheme(value:string|null):Theme { return value==='dark'||value==='system'?value:'light'; }
