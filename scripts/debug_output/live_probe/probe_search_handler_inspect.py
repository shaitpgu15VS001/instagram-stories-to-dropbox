#!/usr/bin/env python3
import time, json, sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright

VIEWER_URL = "https://fastdl.app/en2/instagram-anonymously-viewer"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def inspect_once(method, username="kolbarama"):
    print(f"\n=== Method {method} ===", flush=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        ctx = browser.new_context(user_agent=USER_AGENT, viewport={"width":1280,"height":900}, locale="en-US")
        page = ctx.new_page()
        page.goto(VIEWER_URL, wait_until="domcontentloaded", timeout=15000)
        page.wait_for_selector("#search-form-input", state="visible", timeout=10000)
        # inspect initial DOM
        dom = page.evaluate("""()=>{
            const input = document.querySelector('#search-form-input');
            const btn = document.querySelector('#searchFormButton');
            const form = document.querySelector('form');
            const app = document.querySelector('#app') || document.querySelector('[data-v-app]');
            // try to find Vue
            let vueQuery = null;
            try {
                // Vue 3: try to get component instance
                const el = document.querySelector('#search-form-input');
                if (el && el.__vueParentComponent) vueQuery = 'found __vueParentComponent';
                else if (window.__vue_app__) vueQuery = 'window.__vue_app__ exists';
                else vueQuery = 'no vue found';
            } catch(e){ vueQuery = 'err:'+e.message; }
            return {
                inputValue: input ? input.value : null,
                inputOuter: input ? input.outerHTML.slice(0,500) : null,
                btnOuter: btn ? btn.outerHTML.slice(0,500) : null,
                btnDisabled: btn ? btn.disabled : null,
                btnVisible: btn ? !!(btn.offsetParent) : null,
                btnRect: btn ? btn.getBoundingClientRect().toJSON() : null,
                formOuter: form ? form.outerHTML.slice(0,800) : null,
                formExists: !!form,
                vueHint: vueQuery,
                hasVue: !!window.Vue,
                hasApp: !!document.querySelector('#app'),
                url: location.href
            };
        }""")
        print(f"  before: inputValue='{dom['inputValue']}' btnDisabled={dom['btnDisabled']} vueHint={dom['vueHint']} hasVue={dom['hasVue']}", flush=True)
        print(f"  formExists={dom['formExists']}", flush=True)
        print(f"  btnOuter: {dom['btnOuter'][:200] if dom['btnOuter'] else 'null'}", flush=True)
        print(f"  formOuter: {dom['formOuter'][:400] if dom['formOuter'] else 'null'}", flush=True)

        # attach listeners
        reqs = []
        def on_req(r):
            if "api-wh.fastdl.app" in r.url:
                reqs.append(r.url[:120])
                print(f"    -> REQUEST {r.method} {r.url[:100]}", flush=True)
        page.on("request", on_req)

        # now do method
        if method == "A":
            # current: fill + force click
            print(f"  doing A: fill + force click", flush=True)
            page.fill("#search-form-input", username)
            # check after fill
            after = page.evaluate("""()=>{
                const input=document.querySelector('#search-form-input');
                return {value: input.value, vueVal: (()=>{ try{ const el=document.querySelector('#search-form-input'); return el.value; }catch(e){return 'err'}})()};
            }""")
            print(f"    after fill value='{after['value']}'", flush=True)
            page.click("#searchFormButton", force=True, timeout=5000)
            print(f"    clicked force", flush=True)
        elif method == "B":
            print(f"  doing B: fill + click no force", flush=True)
            page.fill("#search-form-input", username)
            after = page.evaluate("""()=>document.querySelector('#search-form-input').value""")
            print(f"    after fill value='{after}'", flush=True)
            page.click("#searchFormButton", timeout=5000)
            print(f"    clicked no force", flush=True)
        elif method == "C":
            print(f"  doing C: focus + keyboard type + Enter", flush=True)
            page.focus("#search-form-input")
            page.keyboard.type(username, delay=50)
            after = page.evaluate("""()=>document.querySelector('#search-form-input').value""")
            print(f"    after type value='{after}'", flush=True)
            page.keyboard.press("Enter")
            print(f"    pressed Enter", flush=True)
        elif method == "D":
            print(f"  doing D: DOM value + dispatch input/change", flush=True)
            page.evaluate("""(u)=>{
                const input=document.querySelector('#search-form-input');
                input.focus();
                input.value=u;
                input.dispatchEvent(new Event('input', {bubbles:true}));
                input.dispatchEvent(new Event('change', {bubbles:true}));
                // also try Vue-specific
                input.dispatchEvent(new KeyboardEvent('keydown', {bubbles:true, key: 'a'}));
                input.dispatchEvent(new KeyboardEvent('keyup', {bubbles:true, key: 'a'}));
            }""", username)
            after = page.evaluate("""()=>document.querySelector('#search-form-input').value""")
            print(f"    after dispatch value='{after}'", flush=True)
            # then click without force
            page.click("#searchFormButton", timeout=5000)
            print(f"    clicked", flush=True)
        elif method == "E":
            print(f"  doing E: form submit", flush=True)
            page.fill("#search-form-input", username)
            # try to submit form
            hasForm = page.evaluate("""()=>!!document.querySelector('form')""")
            print(f"    hasForm {hasForm}", flush=True)
            page.evaluate("""()=>{
                const form=document.querySelector('form');
                if(form){
                    form.dispatchEvent(new Event('submit', {bubbles:true, cancelable:true}));
                    // also try requestSubmit
                    if(form.requestSubmit) form.requestSubmit();
                }
            }""")
            print(f"    dispatched submit", flush=True)

        # wait 5s for requests
        time.sleep(5)
        print(f"  reqs after 5s: {reqs}", flush=True)
        # check Vue state after
        after_state = page.evaluate("""()=>{
            const input=document.querySelector('#search-form-input');
            // try to find Vue query value via app instance
            let vueVal = null;
            try{
                // search for Vue instance with query
                const els = document.querySelectorAll('*');
                for(const el of els){
                    if(el.__vueParentComponent){
                        const setup = el.__vueParentComponent.setupState || el.__vueParentComponent.data;
                        if(setup && 'query' in setup){ vueVal = setup.query; break; }
                        if(setup && 'form' in setup){ vueVal = JSON.stringify(setup.form).slice(0,200); break; }
                    }
                }
                // also try window
                if(!vueVal && window.__vue_app__){
                    vueVal = 'app exists';
                }
            }catch(e){ vueVal='err:'+e.message; }
            return {inputValue: input.value, vueVal: vueVal, hasUserInfo: !!document.querySelector('.user-info'), tabs: document.querySelectorAll('button.tabs-component__button').length};
        }""")
        print(f"  after 5s: inputValue='{after_state['inputValue']}' vueVal={after_state['vueVal']} hasUserInfo={after_state['hasUserInfo']} tabs={after_state['tabs']}", flush=True)

        browser.close()

for m in ["A","B","C","D","E"]:
    inspect_once(m)
    time.sleep(2)
