import"./CWj6FrbW.js";import"./69_IOA4Y.js";import{p as Ye,g as Ze,x as xe,B as w,y as et,i as tt,c as i,n as u,r as s,l as a,u as k,z as l,k as c,t as q,d as v,a as C,q as R,b as rt,e as at,s as it,m as x,D as X,f as P}from"./DtFjAPax.js";import{i as D}from"./BKqLVPYF.js";import{s as st,c as nt,a as L,r as ot,b as lt}from"./BLgWsK8X.js";import{b as dt}from"./nkKv9Po_.js";import{p as $,b as be}from"./DazRNbaE.js";import{p as ut}from"./Bfc47y5P.js";import{i as ct}from"./CWPhcWBV.js";import{g as ft}from"./pzP2z9pO.js";import{n as Y,e as vt,a as mt}from"./BNweE9gB.js";import{C as _t}from"./C_HspQx1.js";import{C as pt}from"./C3zPP2Tr.js";import{S as gt}from"./Bea1P_wb.js";import{T as Z}from"./D3rnh3OW.js";import{C as ht}from"./BECweHH6.js";import{L as yt}from"./vj1okuxT.js";import{L as we}from"./DBvPOG5D.js";import{P as xt}from"./HjMQZeQW.js";import{p as ee}from"./BAITYFRZ.js";var bt=P('<div class="shrink-0 truncate font-mono"> </div>'),wt=P('<input class="w-full bg-transparent font-mono outline-hidden disabled:text-gray-500" type="text" required=""/>'),kt=P('<select class="h-7 rounded-lg border border-gray-100 bg-transparent px-2 text-xs outline-hidden dark:border-gray-800"><option> </option><option> </option></select>'),$t=P('<div class="text-sm text-gray-500"><div class=" bg-yellow-500/20 text-yellow-700 dark:text-yellow-200 rounded-lg px-4 py-3"><div> </div> <ul class=" mt-1 list-disc pl-4 text-xs"><li> </li> <li> </li></ul></div> <div class="my-3"> </div></div>'),Ft=P('<div class="flex h-full w-full min-w-0 flex-col overflow-hidden"><form class="flex h-full min-h-0 min-w-0 flex-col"><button class="mb-1 flex h-6 w-fit items-center gap-1 rounded-md text-xs text-gray-400 transition-colors duration-75 hover:text-gray-700 dark:text-gray-600 dark:hover:text-gray-300" type="button"><!> <span> </span></button> <div class="flex shrink-0 flex-col gap-2 pb-2 px-1 sm:flex-row sm:items-start"><div class="min-w-0 w-full flex-1"><!> <div class="mt-0.5 flex min-w-0 items-center gap-2 text-xs text-gray-500"><!> <!></div></div> <div class="flex shrink-0 items-center gap-1"><!> <!></div></div> <div class="min-h-0 flex-1 overflow-hidden rounded-lg flex flex-col"><!> <div><!></div></div> <div class="shrink-0 py-2 text-xs text-gray-500"><div class="flex items-center justify-between gap-3"><div class="min-w-0"><span class="font-normal dark:text-gray-200"> </span> <span class="font-normal dark:text-gray-400"> </span></div> <button class="flex h-7 shrink-0 items-center gap-1.5 rounded-lg bg-gray-900 px-2.5 text-xs text-white transition hover:bg-black disabled:opacity-60 dark:bg-gray-100 dark:text-gray-900 dark:hover:bg-white" type="submit"> <!></button></div></div></form></div> <!>',1);function Gt(ke,g){Ye(g,!1);const t=()=>at(Ie,"$i18n",$e),[$e,Fe]=it(),Ie=Ze("i18n");let h=x(""),M=x(null),E=x(!1),z=x(!1),Ne=$(g,"onSave",8,async e=>{}),m=$(g,"edit",8,!1),te=$(g,"clone",8,!1),b=$(g,"id",12,""),p=$(g,"name",12,""),o=$(g,"meta",28,()=>({description:""})),y=$(g,"content",12,""),F=x("");const qe=()=>{c(F,y())};let S=x(),O=x("filter");const re=`"""
title: Example Filter
author: open-webui
author_url: https://github.com/open-webui
funding_url: https://github.com/open-webui
version: 0.1
"""

from pydantic import BaseModel, Field
from typing import Optional


class Filter:
    class Valves(BaseModel):
        priority: int = Field(
            default=0, description="Priority level for the filter operations."
        )
        max_turns: int = Field(
            default=8, description="Maximum allowable conversation turns for a user."
        )
        pass

    class UserValves(BaseModel):
        max_turns: int = Field(
            default=4, description="Maximum allowable conversation turns for a user."
        )
        pass

    def __init__(self):
        # Indicates custom file handling logic. This flag helps disengage default routines in favor of custom
        # implementations, informing the WebUI to defer file-related operations to designated methods within this class.
        # Alternatively, you can remove the files directly from the body in from the inlet hook
        # self.file_handler = True

        # Initialize 'valves' with specific configurations. Using 'Valves' instance helps encapsulate settings,
        # which ensures settings are managed cohesively and not confused with operational flags like 'file_handler'.
        self.valves = self.Valves()
        pass

    def inlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        # Modify the request body or validate it before processing by the chat completion API.
        # This function is the pre-processor for the API where various checks on the input can be performed.
        # It can also modify the request before sending it to the API.
        print(f"inlet:{__name__}")
        print(f"inlet:body:{body}")
        print(f"inlet:user:{__user__}")

        if __user__.get("role", "admin") in ["user", "admin"]:
            messages = body.get("messages", [])

            max_turns = min(__user__["valves"].max_turns, self.valves.max_turns)
            if len(messages) > max_turns:
                raise Exception(
                    f"Conversation turn limit exceeded. Max turns: {max_turns}"
                )

        return body

    def request(self, body: dict, __user__: Optional[dict] = None) -> dict:
        # Modify the request body before each model/provider call.
        print(f"request:{__name__}")
        print(f"request:body:{body}")
        print(f"request:user:{__user__}")

        return body

    def outlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        # Modify or analyze the response body after processing by the API.
        # This function is the post-processor for the API, which can be used to modify the response
        # or perform additional checks and analytics.
        print(f"outlet:{__name__}")
        print(f"outlet:body:{body}")
        print(f"outlet:user:{__user__}")

        return body
`,Ce=`"""
title: Example Event
author: open-webui
author_url: https://github.com/open-webui
funding_url: https://github.com/open-webui
version: 0.1
"""

from pydantic import BaseModel


class Event:
    class Valves(BaseModel):
        pass

    def __init__(self):
        self.valves = self.Valves()

    async def event(
        self,
        event: dict,
        __event_id__: str = None,
        __event_name__: str = None,
        __id__: str = None,
        __app__=None,
        __request__=None,
    ):
        print(f"event:{__name__}")
        print(f"event:id:{__event_id__}")
        print(f"event:name:{__event_name__}")
        print(f"event:payload:{event}")
`;let T=x(re);const Pe=e=>{c(O,e),c(T,e==="event"?Ce:re),y(a(T)),c(F,a(T))},Me=e=>{Pe(e==="event"?"event":"filter")},Ee=async()=>{var e;if(!p().trim()||!((e=o().description)!=null&&e.trim())){c(h,""),toast.error(t().t("Name and description are required"));return}c(E,!0);try{await Ne()({id:b(),name:p(),meta:{...o(),i18n:ee(o().i18n)},content:y()})}finally{c(E,!1)}},ae=async()=>{if(a(S)){y(a(F)),await X();const e=await a(S).formatPythonCodeHandler();await X(),y(a(F)),await X(),e||console.warn("Code formatting failed or was skipped, saving unformatted code"),Ee()}};xe(()=>w(y()),()=>{y()&&qe()}),xe(()=>(w(p()),w(m()),w(te()),Y),()=>{p()&&!m()&&!te()&&b(Y(p()))}),et(),ct();var ie=Ft(),V=tt(ie),B=i(V),A=i(B),se=i(A);ht(se,{className:"size-3",strokeWidth:"2"});var ne=u(se,2),Se=i(ne,!0);s(ne),s(A);var H=u(A,2),U=i(H),oe=i(U);{let e=k(()=>(t(),l(()=>t().t("e.g. My Filter"))));Z(oe,{get content(){return a(e)},placement:"top-start",children:(r,d)=>{{let f=k(()=>(t(),l(()=>t().t("Function Name"))));we(r,{get placeholder(){return a(f)},get locale(){return a(h)},required:!0,get value(){return p()},set value(n){p(n)},get translations(){return o().i18n},set translations(n){o(o().i18n=n,!0)},$$legacy:!0})}},$$slots:{default:!0}})}var le=u(oe,2),de=i(le);{var Te=e=>{var r=bt(),d=i(r,!0);s(r),q(()=>{L(r,"title",b()),v(d,b())}),C(e,r)},Be=e=>{{let r=k(()=>(t(),l(()=>t().t("e.g. my_filter"))));Z(e,{className:"min-w-[8rem] flex-1",get content(){return a(r)},placement:"top-start",children:(d,f)=>{var n=wt();ot(n),q((I,_)=>{L(n,"placeholder",I),L(n,"aria-label",_),n.disabled=m()},[()=>(t(),l(()=>t().t("Function ID"))),()=>(t(),l(()=>t().t("Function ID")))]),dt(n,b),C(d,n)},$$slots:{default:!0}})}};D(de,e=>{m()?e(Te):e(Be,-1)})}var Ae=u(de,2);{let e=k(()=>(t(),l(()=>t().t("e.g. A filter to remove profanity from text"))));Z(Ae,{className:"flex min-w-0 flex-1 items-center",get content(){return a(e)},placement:"top-start",children:(r,d)=>{{let f=k(()=>(t(),l(()=>t().t("Function Description"))));we(r,{get placeholder(){return a(f)},get locale(){return a(h)},field:"description",required:!0,get value(){return o().description},set value(n){o(o().description=n,!0)},get translations(){return o().i18n},set translations(n){o(o().i18n=n,!0)},$$legacy:!0})}},$$slots:{default:!0}})}s(le),s(U);var ue=u(U,2),ce=i(ue);{let e=k(()=>(w(ee),w(o()),l(()=>Object.keys(ee(o().i18n)))));yt(ce,{get translatedLocales(){return a(e)},get value(){return a(h)},set value(r){c(h,r)},$$legacy:!0})}var De=u(ce,2);{var Le=e=>{var r=kt(),d=i(r),f=i(d,!0);s(d),d.value=d.__value="filter";var n=u(d),I=i(n,!0);s(n),n.value=n.__value="event",s(r),q((_,N,Q)=>{L(r,"aria-label",_),v(f,N),v(I,Q)},[()=>(t(),l(()=>t().t("Function starter"))),()=>(t(),l(()=>t().t("Filter"))),()=>(t(),l(()=>t().t("Event")))]),lt(r,()=>a(O),_=>c(O,_)),R("change",r,_=>Me(_.currentTarget.value)),C(e,r)};D(De,e=>{m()||e(Le)})}s(ue),s(H);var W=u(H,2),fe=i(W);{var ze=e=>{{let r=k(()=>m()?b():"");xt(e,{get id(){return a(r)},kind:"function",get locale(){return a(h)},get translations(){return o().i18n},set translations(d){o(o().i18n=d,!0)},$$legacy:!0})}};D(fe,e=>{a(h)&&e(ze)})}var j=u(fe,2),Oe=i(j);be(_t(Oe,{get value(){return y()},lang:"python",get boilerplate(){return a(T)},className:"text-[0.6875rem]",onChange:e=>{if(c(F,e),!m()){const r=vt(e);r.title&&!p()&&(p(mt(r.title)),b(Y(r.title))),r.description&&!o().description&&o({...o(),description:r.description})}},onSave:async()=>{a(M)&&a(M).requestSubmit()},$$legacy:!0}),e=>c(S,e),()=>a(S)),s(j),s(W);var ve=u(W,2),me=i(ve),G=i(me),J=i(G),Ve=i(J,!0);s(J);var _e=u(J),pe=u(_e),He=i(pe,!0);s(pe),s(G);var K=u(G,2),ge=i(K),Ue=u(ge);{var We=e=>{gt(e,{className:"size-3"})};D(Ue,e=>{a(E)&&e(We)})}s(K),s(me),s(ve),s(B),be(B,e=>c(M,e),()=>a(M)),s(V);var je=u(V,2);pt(je,{get show(){return a(z)},set show(e){c(z,e)},$$events:{confirm:()=>{ae()}},children:(e,r)=>{var d=$t(),f=i(d),n=i(f),I=i(n,!0);s(n);var _=u(n,2),N=i(_),Q=i(N,!0);s(N);var he=u(N,2),Ge=i(he,!0);s(he),s(_),s(f);var ye=u(f,2),Je=i(ye,!0);s(ye),s(d),q((Ke,Qe,Re,Xe)=>{v(I,Ke),v(Q,Qe),v(Ge,Re),v(Je,Xe)},[()=>(t(),l(()=>t().t("Please carefully review the following warnings:"))),()=>(t(),l(()=>t().t("Functions allow arbitrary code execution."))),()=>(t(),l(()=>t().t("Do not install functions from sources you do not fully trust."))),()=>(t(),l(()=>t().t("I acknowledge that I have read and I understand the implications of my action. I am aware of the risks associated with executing arbitrary code and I have verified the trustworthiness of the source.")))]),C(e,d)},$$slots:{default:!0},$$legacy:!0}),q((e,r,d,f,n)=>{v(Se,e),st(j,1,nt(a(h)?"hidden":"h-full")),v(Ve,r),v(_e,` ${d??""} `),v(He,f),K.disabled=a(E),v(ge,`${n??""} `)},[()=>(t(),l(()=>t().t("Back"))),()=>(t(),l(()=>t().t("Warning:"))),()=>(t(),l(()=>t().t("Functions can execute arbitrary code."))),()=>(t(),l(()=>t().t("Only install functions from sources you trust."))),()=>(t(),w(m()),l(()=>t().t(m()?"Save":"Save & Create")))]),R("click",A,()=>{ft("/admin/functions")}),R("submit",B,ut(()=>{m()?ae():c(z,!0)})),C(ke,ie),rt(),Fe()}export{Gt as F};
//# sourceMappingURL=D5XiYihB.js.map
