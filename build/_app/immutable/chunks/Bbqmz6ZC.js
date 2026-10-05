import"./CWj6FrbW.js";import"./69_IOA4Y.js";import{p as Xe,g as Ze,x as we,B as C,y as et,i as tt,k as _,l as a,n as d,c as i,r as o,u as g,z as n,t as G,d as y,a as M,q as be,b as rt,e as ke,s as at,m as E,D as K,f as F}from"./DtFjAPax.js";import{i as J}from"./BKqLVPYF.js";import{s as st,c as it,a as Q,r as ot}from"./BLgWsK8X.js";import{b as nt}from"./nkKv9Po_.js";import{p as $,b as $e}from"./DazRNbaE.js";import{p as lt}from"./Bfc47y5P.js";import{i as dt}from"./CWPhcWBV.js";import{t as V}from"./B4BhJv0K.js";import{g as ut}from"./pzP2z9pO.js";import{u as ct}from"./DcFgEIHw.js";import{u as mt}from"./VmaDGz8e.js";import{n as X,e as ft,a as pt}from"./BNweE9gB.js";import{C as vt}from"./C_HspQx1.js";import{C as _t}from"./C3zPP2Tr.js";import{C as gt}from"./BECweHH6.js";import{T as Z}from"./D3rnh3OW.js";import{A as ht,a as yt}from"./CmE73aLB.js";import{S as xt}from"./Bea1P_wb.js";import{L as wt}from"./vj1okuxT.js";import{L as Te}from"./DBvPOG5D.js";import{P as bt}from"./HjMQZeQW.js";import{p as ee}from"./BAITYFRZ.js";var kt=F('<div class="shrink-0 truncate font-mono"> </div>'),$t=F('<input class="w-full bg-transparent font-mono outline-hidden disabled:text-gray-500" type="text" required=""/>'),Tt=F('<div class="text-sm text-gray-500"><div class=" bg-yellow-500/20 text-yellow-700 dark:text-yellow-200 rounded-lg px-4 py-3"><div> </div> <ul class=" mt-1 list-disc pl-4 text-xs"><li> </li> <li> </li></ul></div> <div class="my-3"> </div></div>'),Ct=F('<!> <div class="flex h-full w-full min-w-0 flex-col overflow-hidden"><form class="flex h-full min-h-0 min-w-0 flex-col"><button class="mb-1 flex h-6 w-fit items-center gap-1 rounded-md text-xs text-gray-400 transition-colors duration-75 hover:text-gray-700 dark:text-gray-600 dark:hover:text-gray-300" type="button"><!> <span> </span></button> <div class="flex shrink-0 flex-col gap-2 pb-2 px-1 sm:flex-row sm:items-start"><div class="min-w-0 w-full flex-1"><!> <div class="mt-0.5 flex min-w-0 items-center gap-2 text-xs text-gray-500"><!> <!></div></div> <div class="flex shrink-0 items-center gap-1 pr-0.5"><!> <!></div></div> <div class="min-h-0 flex-1 overflow-hidden rounded-lg flex flex-col"><!> <div><!></div></div> <div class="shrink-0 py-2 text-xs text-gray-500"><div class="flex items-center justify-between gap-3"><div class="min-w-0"><span class="font-normal dark:text-gray-200"> </span> <span class="font-normal dark:text-gray-400"> </span></div> <button class="flex h-7 shrink-0 items-center gap-1.5 rounded-lg bg-gray-900 px-2.5 text-xs text-white transition hover:bg-black disabled:opacity-60 dark:bg-gray-100 dark:text-gray-900 dark:hover:bg-white" type="submit"> <!></button></div></div></form></div> <!>',1);function Vt(Ce,x){Xe(x,!1);const r=()=>ke(qe,"$i18n",te),p=()=>ke(ct,"$user",te),[te,Ee]=at(),qe=Ze("i18n");let k=E(""),q=E(null),P=E(!1),L=E(!1),H=E(!1),h=$(x,"edit",8,!1),re=$(x,"clone",8,!1),Pe=$(x,"onSave",8,async e=>{}),w=$(x,"id",12,""),b=$(x,"name",12,""),l=$(x,"meta",28,()=>({description:""})),T=$(x,"content",12,""),I=$(x,"accessGrants",28,()=>[]),A=E("");const Ie=()=>{_(A,T())};let S=E(),Ae=`import os
import requests
from datetime import datetime
from pydantic import BaseModel, Field

class Tools:
    def __init__(self):
        pass

    # Add your custom tools using pure Python code here, make sure to add type hints and descriptions
	
    def get_user_name_and_email_and_id(self, __user__: dict = {}) -> str:
        """
        Get the user name, Email and ID from the user object.
        """

        # Do not include a descrption for __user__ as it should not be shown in the tool's specification
        # The session user object will be passed as a parameter when the function is called

        print(__user__)
        result = ""

        if "name" in __user__:
            result += f"User: {__user__['name']}"
        if "id" in __user__:
            result += f" (ID: {__user__['id']})"
        if "email" in __user__:
            result += f" (Email: {__user__['email']})"

        if result == "":
            result = "User: Unknown"

        return result

    def get_current_time(self) -> str:
        """
        Get the current time in a more human-readable format.
        """

        now = datetime.now()
        current_time = now.strftime("%I:%M:%S %p")  # Using 12-hour format with AM/PM
        current_date = now.strftime(
            "%A, %B %d, %Y"
        )  # Full weekday, month name, day, and year

        return f"Current Date and Time = {current_date}, {current_time}"

    def calculator(
        self,
        equation: str = Field(
            ..., description="The mathematical equation to calculate."
        ),
    ) -> str:
        """
        Calculate the result of an equation.
        """

        # Avoid using eval in production code
        # https://nedbatchelder.com/blog/201206/eval_really_is_dangerous.html
        try:
            result = eval(equation)
            return f"{equation} = {result}"
        except Exception as e:
            print(e)
            return "Invalid equation"

    def get_current_weather(
        self,
        city: str = Field(
            "New York, NY", description="Get the current weather for a given city."
        ),
    ) -> str:
        """
        Get the current weather for a given city.
        """

        api_key = os.getenv("OPENWEATHER_API_KEY")
        if not api_key:
            return (
                "API key is not set in the environment variable 'OPENWEATHER_API_KEY'."
            )

        base_url = "http://api.openweathermap.org/data/2.5/weather"
        params = {
            "q": city,
            "appid": api_key,
            "units": "metric",  # Optional: Use 'imperial' for Fahrenheit
        }

        try:
            response = requests.get(base_url, params=params)
            response.raise_for_status()  # Raise HTTPError for bad responses (4xx and 5xx)
            data = response.json()

            if data.get("cod") != 200:
                return f"Error fetching weather data: {data.get('message')}"

            weather_description = data["weather"][0]["description"]
            temperature = data["main"]["temp"]
            humidity = data["main"]["humidity"]
            wind_speed = data["wind"]["speed"]

            return f"Weather in {city}: {temperature}°C"
        except requests.RequestException as e:
            return f"Error fetching weather data: {str(e)}"
`;const Se=async()=>{var e;if(!b().trim()||!((e=l().description)!=null&&e.trim())){_(k,""),V.error(r().t("Name and description are required"));return}_(P,!0);try{await Pe()({id:w(),name:b(),meta:{...l(),i18n:ee(l().i18n)},content:T(),access_grants:I()})}finally{_(P,!1)}},ae=async()=>{if(a(S)){T(a(A)),await K();const e=await a(S).formatPythonCodeHandler();await K(),T(a(A)),await K(),e||console.warn("Code formatting failed or was skipped, saving unformatted code"),Se()}};we(()=>C(T()),()=>{T()&&Ie()}),we(()=>(C(b()),C(h()),C(re()),X),()=>{b()&&!h()&&!re()&&w(X(b()))}),et(),dt();var se=Ct(),ie=tt(se);{let e=g(()=>(p(),n(()=>{var t,m,u,f;return((u=(m=(t=p())==null?void 0:t.permissions)==null?void 0:m.sharing)==null?void 0:u.tools)||((f=p())==null?void 0:f.role)==="admin"}))),s=g(()=>(p(),n(()=>{var t,m,u,f;return((u=(m=(t=p())==null?void 0:t.permissions)==null?void 0:m.sharing)==null?void 0:u.public_tools)||((f=p())==null?void 0:f.role)==="admin"}))),c=g(()=>(p(),n(()=>{var t,m,u,f;return(((u=(m=(t=p())==null?void 0:t.permissions)==null?void 0:m.access_grants)==null?void 0:u.allow_users)??!0)||((f=p())==null?void 0:f.role)==="admin"}))),v=g(()=>(p(),n(()=>{var t,m,u,f;return(((u=(m=(t=p())==null?void 0:t.permissions)==null?void 0:m.access_grants)==null?void 0:u.allow_groups)??!0)||((f=p())==null?void 0:f.role)==="admin"})));ht(ie,{accessRoles:["read","write"],get share(){return a(e)},get sharePublic(){return a(s)},get shareUsers(){return a(c)},get allowGroups(){return a(v)},onChange:async()=>{if(h()&&w())try{await mt(localStorage.token,w(),I()),V.success(r().t("Saved"))}catch(t){V.error(`${t}`)}},get show(){return a(H)},set show(t){_(H,t)},get accessGrants(){return I()},set accessGrants(t){I(t)},$$legacy:!0})}var U=d(ie,2),N=i(U),D=i(N),oe=i(D);gt(oe,{className:"size-3",strokeWidth:"2"});var ne=d(oe,2),Ne=i(ne,!0);o(ne),o(D);var j=d(D,2),B=i(j),le=i(B);{let e=g(()=>(r(),n(()=>r().t("e.g. My Tools"))));Z(le,{get content(){return a(e)},placement:"top-start",children:(s,c)=>{{let v=g(()=>(r(),n(()=>r().t("Tool Name"))));Te(s,{get placeholder(){return a(v)},showControls:!1,get locale(){return a(k)},required:!0,get value(){return b()},set value(t){b(t)},get translations(){return l().i18n},set translations(t){l(l().i18n=t,!0)},$$legacy:!0})}},$$slots:{default:!0}})}var de=d(le,2),ue=i(de);{var De=e=>{var s=kt(),c=i(s,!0);o(s),G(()=>{Q(s,"title",w()),y(c,w())}),M(e,s)},Ge=e=>{{let s=g(()=>(r(),n(()=>r().t("e.g. my_tools"))));Z(e,{className:"min-w-[8rem] flex-1",get content(){return a(s)},placement:"top-start",children:(c,v)=>{var t=$t();ot(t),G((m,u)=>{Q(t,"placeholder",m),Q(t,"aria-label",u),t.disabled=h()},[()=>(r(),n(()=>r().t("Tool ID"))),()=>(r(),n(()=>r().t("Tool ID")))]),nt(t,w),M(c,t)},$$slots:{default:!0}})}};J(ue,e=>{h()?e(De):e(Ge,-1)})}var Me=d(ue,2);{let e=g(()=>(r(),n(()=>r().t("e.g. Tools for performing various operations"))));Z(Me,{className:"flex min-w-0 flex-1 items-center",get content(){return a(e)},placement:"top-start",children:(s,c)=>{{let v=g(()=>(r(),n(()=>r().t("Tool Description"))));Te(s,{get placeholder(){return a(v)},showControls:!1,get locale(){return a(k)},field:"description",required:!0,get value(){return l().description},set value(t){l(l().description=t,!0)},get translations(){return l().i18n},set translations(t){l(l().i18n=t,!0)},$$legacy:!0})}},$$slots:{default:!0}})}o(de),o(B);var ce=d(B,2),me=i(ce);{let e=g(()=>(C(ee),C(l()),n(()=>Object.keys(ee(l().i18n)))));wt(me,{get translatedLocales(){return a(e)},get value(){return a(k)},set value(s){_(k,s)},$$legacy:!0})}var Fe=d(me,2);yt(Fe,{$$events:{click:()=>{_(H,!0)}}}),o(ce),o(j);var O=d(j,2),fe=i(O);{var Le=e=>{{let s=g(()=>h()?w():"");bt(e,{get id(){return a(s)},kind:"tool",get locale(){return a(k)},get translations(){return l().i18n},set translations(c){l(l().i18n=c,!0)},$$legacy:!0})}};J(fe,e=>{a(k)&&e(Le)})}var R=d(fe,2),He=i(R);$e(vt(He,{get value(){return T()},lang:"python",boilerplate:Ae,className:"text-[0.6875rem]",onChange:e=>{if(_(A,e),!h()){const s=ft(e);s.title&&!b()&&(b(pt(s.title)),w(X(s.title))),s.description&&!l().description&&l({...l(),description:s.description})}},onSave:async()=>{a(q)&&a(q).requestSubmit()},$$legacy:!0}),e=>_(S,e),()=>a(S)),o(R),o(O);var pe=d(O,2),ve=i(pe),W=i(ve),Y=i(W),Ue=i(Y,!0);o(Y);var _e=d(Y),ge=d(_e),je=i(ge,!0);o(ge),o(W);var z=d(W,2),he=i(z),Be=d(he);{var Oe=e=>{xt(e,{className:"size-3"})};J(Be,e=>{a(P)&&e(Oe)})}o(z),o(ve),o(pe),o(N),$e(N,e=>_(q,e),()=>a(q)),o(U);var Re=d(U,2);_t(Re,{get show(){return a(L)},set show(e){_(L,e)},$$events:{confirm:()=>{ae()}},children:(e,s)=>{var c=Tt(),v=i(c),t=i(v),m=i(t,!0);o(t);var u=d(t,2),f=i(u),We=i(f,!0);o(f);var ye=d(f,2),Ye=i(ye,!0);o(ye),o(u),o(v);var xe=d(v,2),ze=i(xe,!0);o(xe),o(c),G((Ke,Je,Qe,Ve)=>{y(m,Ke),y(We,Je),y(Ye,Qe),y(ze,Ve)},[()=>(r(),n(()=>r().t("Please carefully review the following warnings:"))),()=>(r(),n(()=>r().t("Tools have a function calling system that allows arbitrary code execution."))),()=>(r(),n(()=>r().t("Do not install tools from sources you do not fully trust."))),()=>(r(),n(()=>r().t("I acknowledge that I have read and I understand the implications of my action. I am aware of the risks associated with executing arbitrary code and I have verified the trustworthiness of the source.")))]),M(e,c)},$$slots:{default:!0},$$legacy:!0}),G((e,s,c,v,t)=>{y(Ne,e),st(R,1,it(a(k)?"hidden":"h-full")),y(Ue,s),y(_e,` ${c??""} `),y(je,v),z.disabled=a(P),y(he,`${t??""} `)},[()=>(r(),n(()=>r().t("Back"))),()=>(r(),n(()=>r().t("Warning:"))),()=>(r(),n(()=>r().t("Tools can execute arbitrary code."))),()=>(r(),n(()=>r().t("Only install tools from sources you trust."))),()=>(r(),C(h()),n(()=>r().t(h()?"Save":"Save & Create")))]),be("click",D,()=>{ut("/workspace/tools")}),be("submit",N,lt(()=>{h()?ae():_(L,!0)})),M(Ce,se),rt(),Ee()}export{Vt as T};
//# sourceMappingURL=Bbqmz6ZC.js.map
