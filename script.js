// Same-origin. If you host the API elsewhere, set API_BASE to that URL.
const API_BASE = "";
const sessionId = (crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Date.now());

// Elements
const startWizard = document.getElementById("startWizard");
const wizardContent = document.getElementById("wizardContent");
const wForm = document.getElementById("w-form");
const wTitle = document.getElementById("w-title");
const wDesc = document.getElementById("w-desc");
const wPrev = document.getElementById("w-prev");
const wNext = document.getElementById("w-next");
const wBar = document.getElementById("w-bar");
const wIdx = document.getElementById("w-idx");
const wTotal = document.getElementById("w-total");

const chatContainer = document.getElementById("chatContainer");
const chatBody = document.getElementById("chatBody");
const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");
const chipRow = document.getElementById("chipRow");

// Wizard model
const model = { goal: "", timeline: "" };
const STEPS = [
  {
    title: "What brings you in today?",
    desc:  "Choose the option that best matches your goal.",
    type:  "radio", key: "goal",
    options: ["First home","Refinance","Investor","Upgrade","Construction"]
  },
  {
    title: "What’s your timeline?",
    desc:  "Roughly when are you hoping to move ahead?",
    type:  "radio", key: "timeline",
    options: ["ASAP (0–1 month)","Soon (1–3 months)","Planning (3–6 months)","Exploring (6+ months)"]
  }
];
wTotal.textContent = String(STEPS.length);
let step = 0;

// Start wizard
startWizard.addEventListener("click", ()=>{
  wizardContent.classList.remove("hidden");
  window.scrollTo({ top: wizardContent.getBoundingClientRect().top + window.scrollY - 20, behavior: "smooth" });
  renderStep();
});

// Render a step
function renderStep(){
  const s = STEPS[step];
  wTitle.innerText = s.title;
  wDesc.innerText  = s.desc;
  wIdx.innerText   = String(step+1);
  wBar.style.width = `${((step+1)/STEPS.length)*100}%`;

  wForm.innerHTML = "";
  const wrap = document.createElement("div");
  (s.options || []).forEach(opt=>{
    const row = document.createElement("label");
    row.className = "opt";
    row.innerHTML = `<input type="radio" name="${s.key}" value="${opt}"><div class="label">${opt}</div>`;
    const input = row.querySelector("input");
    if (model[s.key] === opt) input.checked = true;
    input.onchange = ()=>{ model[s.key] = opt; };
    wrap.appendChild(row);
  });
  wForm.appendChild(wrap);

  wPrev.disabled = step === 0;
  wNext.textContent = step === STEPS.length-1 ? "Finish" : "Next";
}

// Nav
wPrev.addEventListener("click", ()=>{ if (step>0){ step--; renderStep(); }});
wNext.addEventListener("click", async ()=>{
  const s = STEPS[step];
  if (!model[s.key]) { alert("Please choose one option."); return; }

  if (step < STEPS.length-1){ step++; renderStep(); return; }

  // FINISH → prime backend, then flip to chat
  try{
    await fetch(`${API_BASE}/prime`, {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({ session_id: sessionId, goal: model.goal, timeline: model.timeline })
    });
  }catch(_){}

  // Replace wizard with chat in same card
  wizardContent.classList.add("hidden");
  chatContainer.classList.remove("hidden");
  // animate in
  requestAnimationFrame(()=> chatContainer.classList.add("show"));

  // kick off conversation so Finny asks for the user's name inside chat
  await safeSend("start", false);
});

// ------------ Chat ------------
chatForm.addEventListener("submit", async (e)=>{
  e.preventDefault();
  const text = chatInput.value.trim();
  if (!text) return;
  addBubble(text, "user");
  chatInput.value = "";
  clearChips();
  scrollBottom();
  await safeSend(text, true);
});

async function safeSend(text, showChips){
  const typing = addTyping();
  try{
    const res = await fetch(`${API_BASE}/chat`, {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({ session_id: sessionId, message: text })
    });
    const data = await res.json();
    typing.remove();

    addBubble(data.reply, "bot");
    if (Array.isArray(data.chips) && data.chips.length) renderChips(data.chips);
    else if (showChips) renderChips(["What documents do I need?","What’s the process?","Book a broker call"]);

    if (data.escalation){
      addBubble("This looks like it needs a broker. I can book a quick call and make sure we meet Best Interests Duty.", "bot");
    }
  } catch {
    typing.remove();
    addBubble("Sorry, I hit a snag. Please try again or speak with a broker.", "bot");
  } finally {
    scrollBottom();
  }
}

// UI helpers
function addBubble(text, who="bot"){
  const div = document.createElement("div");
  div.className = `${who} msg`;
  div.innerHTML = text.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
  chatBody.appendChild(div);
}
function addTyping(){
  const wrap=document.createElement("div"); wrap.className="bot msg";
  const t=document.createElement("div"); t.className="typing";
  t.innerHTML=`<span class="dot"></span><span class="dot"></span><span class="dot"></span>`;
  wrap.appendChild(t); chatBody.appendChild(wrap); return wrap;
}
function renderChips(opts){
  chipRow.innerHTML = "";
  opts.forEach(label=>{
    const b=document.createElement("button");
    b.type="button"; b.className="chip"; b.textContent=label;
    b.onclick=()=> sendChip(label);
    chipRow.appendChild(b);
  });
}
async function sendChip(label){
  addBubble(label,"user");
  clearChips();
  scrollBottom();
  await safeSend(label, false);
}
function clearChips(){ chipRow.innerHTML=""; }
function scrollBottom(){ chatBody.scrollTop = chatBody.scrollHeight; }
