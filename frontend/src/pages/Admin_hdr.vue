<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
const isAdmin = ref(false), loading = ref(true)
onMounted(async () => { try { isAdmin.value = (await fetch('/api/admin/whoami').then(r=>r.json())).is_admin } catch { isAdmin.value = false }; loading.value = false })
async function api(m: string, u: string, b?: any) { const o: RequestInit = { method: m, headers: {} }; if (b) { o.headers = { 'Content-Type': 'application/json' }; o.body = JSON.stringify(b) }; const r = await fetch(u, o); const d = await r.json().catch(()=>({})); if (r.status===401) { alert('登录已过期'); location.href='/'; throw Error('x') }; if (r.status===403) { alert(d.detail||'权限不足'); throw Error('x') }; if (!r.ok) throw Error(d.detail||('HTTP '+r.status)); return d }
function fmt(ts:number) { return ts ? new Date(ts*1000).toLocaleString('zh-CN') : '' }
function fmtShort(ts:number) { if(!ts)return ''; const d=new Date(ts*1000); return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')+' '+String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0') }
function relTime(ts:number) { if(!ts)return '从未'; const n=Date.now(),t=ts*1000,dm=Math.floor((n-t)/60000); if(dm<1)return '刚刚'; if(dm<60)return dm+' 分钟前'; if(dm<1440)return Math.floor(dm/60)+' 小时前'; return fmt(ts) }
function copyText(text:string,btn:HTMLElement|null) { navigator.clipboard.writeText(text).then(()=>{if(btn){const o=btn.textContent;btn.textContent='? 已复制';btn.classList.add('bg-green-100','text-green-600');setTimeout(()=>{btn.textContent=o;btn.classList.remove('bg-green-100','text-green-600')},1500)}}).catch(()=>{}) }
</script>