// demo: the guest's side of the public demo. Out of turn a page of its own covers the house: the wait and place in
// line (it enters by itself), or the summary of a turn that ended. In control: the header pill, bottom tabs Map /
// Devices, the simulation panel beside the map, toasts and map highlights when a rule fires, an intro on the first
// turn (how the flat was set up). What the demo refuses is greyed or hidden before any press (static/greyed.json,
// each entry a refused route). A tab beats every 9 s in control, every 3 s in line.
(function () {
  if (!window.RESTRICTED) return;
  const E = s => Home.escapeHtml(String(s == null ? '' : s));
  const NA = 'Not available in demo';
  const ROOMS = {living: 'Living room', kitchen: 'Kitchen', bedroom: 'Bedroom', kids: 'Kids room', hall: 'Hallway', bath: 'Bathroom'};
  let pill = null, st = null, note = '', noteUntil = 0, sim = {}, feed = [], after = 0, mapIdx = null, simBox = null, lastRole = '';
  let fails = 0, ready = false, looked = false;
  const done = new Set(JSON.parse(sessionStorage.getItem('demo-done') || '[]'));
  const mmss = s => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  const control = () => st && st.role === 'control';
  window.RESTRICTED_EDIT = control;                 // the map: the guest in control edits it like the owner
  const plural = (n, w) => `${n || 0} ${w}${n === 1 ? '' : 's'}`;

  const css = document.createElement('style');
  css.textContent = `
    .demo-pill { display: inline-flex; gap: 6px; align-items: center; font-size: 13px; margin-right: 8px; white-space: nowrap; min-width: 0; }
    .demo-pill > * { flex: none; }
    .demo-pill .tag { overflow: hidden; text-overflow: ellipsis; flex: 0 1 auto; min-width: 0; }
    .demo-pill .tag { padding: 4px 10px; border-radius: 999px; background: #2a333d; }
    .demo-pill .tag.ctl { background: #1f6f43; }
    .demo-pill button, .demo-btn { font: inherit; font-size: 13px; padding: 4px 12px; border-radius: 999px; border: 1px solid #3d8bfd;
      background: transparent; color: inherit; cursor: pointer; white-space: nowrap; }
    .demo-pill button.main { background: #3d8bfd; color: #fff; }
    .demo-pill button.replay { display: inline-flex; align-items: center; gap: 4px; } .demo-pill button.replay svg { flex: none; }
    @media (max-width: 640px) { .demo-pill button.replay { padding: 4px 8px; } }
    .demo-off { opacity: .4 !important; cursor: not-allowed !important; filter: grayscale(1); }
    .demo-veil { position: fixed; left: 50%; top: 8px; transform: translateX(-50%); display: none; background: #3a2a10; border: 1px solid #ffb020;
      color: #fff; font-size: 14px; padding: 6px 14px; border-radius: 999px; z-index: calc(var(--z-toast, 9800) + 100); pointer-events: none; }
    .demo-btn.off { opacity: .45; cursor: not-allowed; }
    .demo-flash { animation: demoflash 1.2s ease-in-out 2; border-radius: 8px; }
    @keyframes demoflash { 50% { box-shadow: 0 0 0 3px #ffc34d; } }
    .demo-veil.on { display: flex; }
    .demo-toasts { position: fixed; left: 50%; bottom: 76px; transform: translateX(-50%); display: flex; flex-direction: column; gap: 6px;
      z-index: var(--z-toast, 9800); pointer-events: none; width: min(92vw, 460px); }
    .demo-toast { background: #1a2129; border: 1px solid #3d8bfd; border-left-width: 4px; border-radius: 10px; padding: 8px 12px; font-size: 14px;
      box-shadow: 0 4px 16px rgba(0,0,0,.5); animation: demoin .25s ease-out; }
    .demo-toast b { color: #8ab4ff; font-weight: 600; }
    @keyframes demoin { from { transform: translateY(10px); opacity: 0 } to { transform: none; opacity: 1 } }
    [data-id].demo-hl { outline: 4px solid #ffc34d !important; outline-offset: 3px; border-radius: 50%; animation: demohl 1s ease-in-out 3; z-index: 20 !important; }
    @keyframes demohl { 50% { outline-color: rgba(255,195,77,.2) } }
    .demo-bottom { display: none; position: fixed; left: 0; right: 0; bottom: 0; background: #11161d; border-top: 1px solid #2a333d; z-index: var(--z-bar, 8000);
      padding-bottom: env(safe-area-inset-bottom); }
    .demo-bottom button { flex: 1; background: none; border: 0; color: #9aa7b3; font: inherit; font-size: 13px; padding: 9px 0 10px; cursor: pointer; }
    .demo-bottom button.on { color: #fff; box-shadow: inset 0 3px 0 #3d8bfd; }
    .demo-bottom button span { display: block; height: 20px; } .demo-bottom button svg { display: block; margin: 0 auto; }
    .demo-panel { padding: 8px 4px 16px; max-width: 900px; }
    .demo-panel h3 { margin: 18px 0 8px; font-size: 15px; }
    .demo-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
    .demo-row .demo-btn.sel { background: #3d8bfd; color: #fff; }
    .demo-btn:disabled { opacity: .45; cursor: not-allowed; }
    .demo-dim { color: #9aa7b3; font-size: 13px; }
    .demo-task { display: flex; gap: 10px; padding: 8px 0; border-bottom: 1px solid #2a333d; font-size: 14px; align-items: center; }
    .demo-task .txt { flex: 1; min-width: 0; } .demo-task .see { display: block; color: #9aa7b3; font-size: 12px; margin-top: 2px; }
    .demo-task { flex-wrap: wrap; } .demo-task .demo-btn { flex: none; } .demo-task .tstate, .demo-task [data-a=press] { min-width: 96px; }
    .demo-task .tstate svg { vertical-align: -2px; } .demo-task .toggle.off { opacity: .45; }
    .demo-task .tac { display: flex; gap: 6px; align-items: center; flex-basis: 100%; order: 3; }        /* under the name and its check */
    .demo-task .tac .tmode svg { display: block; margin: 0 auto; } .demo-task .tac .tmode.sel { background: #3d8bfd; color: #fff; }
    .demo-task .tac b { min-width: 34px; text-align: center; } .demo-task .tac .demo-btn { min-width: 34px; padding: 4px 0; }
    .demo-task .ck { flex: none; width: 20px; height: 20px; border-radius: 50%; border: 2px solid #3d8bfd; text-align: center; line-height: 16px; font-size: 13px; }
    .demo-task.ok .ck { background: #1f6f43; border-color: #1f6f43; }
    .demo-feed { font-size: 13px; line-height: 1.5; }
    .demo-log { display: flex; flex-direction: column; gap: 8px; max-height: 40vh; overflow-y: auto; }
    .demo-bub { align-self: flex-start; max-width: 85%; padding: 8px 12px; border-radius: 12px; background: #232a36; border: 1px solid #2c3442; font-size: 15px; line-height: 1.35; }
    .demo-bub.mine { align-self: flex-end; background: #177A75; border-color: #177A75; color: #fff; }
    .demo-feed div { padding: 3px 0; border-bottom: 1px solid #1f262e; }
    .demo-cap { position: fixed; left: 50%; bottom: 84px; transform: translateX(-50%); z-index: calc(var(--z-dialog, 9000) + 500); width: min(92vw, 560px); background: #1a2129;
      border: 1px solid #3d8bfd; border-radius: 12px; padding: 12px 16px; font-size: 15px; box-shadow: 0 6px 24px rgba(0,0,0,.6); }
    .demo-cap .bar { height: 3px; background: #3d8bfd; margin-top: 10px; transition: width 4s linear; }
    .demo-menu { position: fixed; right: 8px; top: 64px; background: #1a2129; border: 1px solid #2a333d; border-radius: 10px; z-index: var(--z-pop, 8500);
      display: flex; flex-direction: column; min-width: 180px; }
    .demo-menu button { background: none; border: 0; color: inherit; font: inherit; text-align: left; padding: 10px 14px; cursor: pointer; }
    .demo-menu button:hover { background: #222b35; }
    @media (max-width: 1500px) { header .btn-text { display: none; } }   /* icons only: the header never wraps when the owner's buttons come with control */
    [data-m=underlay], body:not(.demo-ctl) [data-m=left], body:not(.demo-ctl) [data-m=walltool], body:not(.demo-ctl) [data-m=optool] { display: none !important; }   /* the owner's map tools: the guest in control only */
    .demo-side { display: none; position: fixed; left: 0; z-index: var(--z-side, 7000); background: #0f141a; flex-direction: column; bottom: var(--demo-bb, 0px); }
    body.demo-map .demo-side { display: flex; }
    .demo-side .shead { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-bottom: 1px solid #2a333d; flex: none; }
    .demo-side .shead b { font-size: 15px; } .demo-side .shead .demo-dim { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .demo-side .sfold { flex: none; width: 30px; height: 30px; border-radius: 50%; border: 1px solid #2a333d; background: none; color: inherit; font-size: 18px; cursor: pointer; }
    .demo-side .sbody { flex: 1; overflow: auto; padding: 0 12px; overscroll-behavior: contain; }
    .demo-side .sbody .demo-panel { padding-top: 0; } .demo-side .sbody h3:first-child { margin-top: 10px; }
    .demo-side .sgrip { display: none; }
    .demo-wait { position: fixed; inset: 0; z-index: 2147483000; background: #0f1419; display: none; align-items: center; justify-content: center; }
    body.demo-waiting .demo-wait { display: flex; } body.demo-waiting { overflow: hidden; }
    .demo-wait .card { width: min(380px, 92vw); background: #1a2129; border: 1px solid #2a333d; border-radius: 14px; padding: 24px; font-size: 15px; }
    .demo-wait h1 { font-size: 20px; margin: 0 0 8px; } .demo-wait .big { font-size: 18px; color: #8ab4ff; margin: 0 0 10px; }
    .demo-wait p { margin: 0 0 12px; } .demo-wait .err { color: #ff7b72; font-size: 14px; }
    .demo-wait .demo-row { margin-top: 16px; } .demo-wait .demo-btn.main { background: #3d8bfd; color: #fff; }
    body.demo-wide .demo-side { top: var(--demo-top, 0px); width: 320px; border-right: 1px solid #2a333d; }
    body.demo-wide.demo-map #app { margin-left: 320px; }
    body.demo-wide.demo-fold .demo-side { width: 44px; } body.demo-wide.demo-fold.demo-map #app { margin-left: 44px; }
    body.demo-wide.demo-fold .demo-side .sbody, body.demo-wide.demo-fold .demo-side .shead > :not(.sfold) { display: none; }
    body.demo-wide.demo-fold .demo-side .shead { padding: 8px 6px; border: 0; }
    body:not(.demo-wide) .demo-side { right: 0; height: var(--demo-sh, 45vh); border-top: 1px solid #2a333d; border-radius: 14px 14px 0 0;
      box-shadow: 0 -6px 20px rgba(0,0,0,.5); transition: height .2s; }
    body:not(.demo-wide) .demo-side.drag { transition: none; }
    body:not(.demo-wide) .demo-side .sgrip { display: block; flex: none; height: 16px; touch-action: none; cursor: grab; }
    body:not(.demo-wide) .demo-side .sgrip::after { content: ""; display: block; width: 40px; height: 4px; border-radius: 2px; background: #3a4552; margin: 8px auto 0; }
    body:not(.demo-wide) .demo-side .shead { touch-action: none; padding-top: 2px; }
    body:not(.demo-wide) .demo-side .sfold { display: none; }
    body.demo-map.demo-wide .demo-toasts { left: auto; right: 16px; transform: none; bottom: auto; top: calc(var(--demo-top, 0px) + 60px); width: min(380px, 40vw); }
    .pf.sheet { bottom: var(--demo-bb, 0px) !important; }          /* the floating panel's phone sheet above the bottom tabs */
    body.demo-map:not(.demo-wide) .demo-toasts { bottom: auto; top: calc(var(--demo-top, 0px) + 8px); }      /* over the plan's top: its rest shows above the sheet */
    body.demo-map:not(.demo-wide) .demo-cap { bottom: calc(var(--demo-bb, 0px) + var(--demo-sh, 45vh) + 10px); }
    @media (max-width: 900px) { .demo-bottom { display: flex; } body.demo-on { padding-bottom: 64px; } .demo-cap { bottom: 80px; } }
    body.stx-open .demo-cap, body.stx-open .demo-intro { display: none; }   /* the tour waits while Settings is open */
    .demo-why { max-width: 860px; margin: 6px 0 14px; padding: 10px 14px; border-radius: 12px; background: #16263a;
      border: 1px solid #2b4566; color: #cfe0f5; font-size: 14px; line-height: 1.45; }
    .demo-why b { color: #fff; } .demo-why p { margin: 4px 0; } .demo-why .dm { color: #9fb6cf; font-size: 13px; }
    .demo-hint { margin: 2px 0 8px; padding: 4px 10px; border-left: 3px solid #3b6ea5; color: #a9c1db; font-size: 12.5px;
      line-height: 1.4; max-width: 860px; }
    .demo-hint b { color: #dbe8f6; font-weight: 600; }
    .demo-why .demo-onpage { margin-top: 8px; border-top: 1px solid #2b4566; padding-top: 6px; } .demo-why .demo-onpage .demo-hint { margin: 3px 0; }
    .demo-items { max-width: 860px; } .demo-items h3 { margin: 18px 0 6px; font-size: 15px; color: #e6eef8; }
    .demo-item { padding: 9px 12px; margin: 6px 0; border: 1px solid rgba(148,163,184,.22); border-radius: 10px; }
    .demo-item b { display: block; color: #fff; margin-bottom: 2px; } .demo-item span { color: #b8c8da; font-size: 13.5px; line-height: 1.45; }
    @media (max-width: 640px) {
      body.demo-on #add-device-btn, body.demo-on #gearbtn, body.demo-on .demo-hide-narrow { display: none !important; }   /* the gear: in the menu */
      .demo-pill .wide { display: none; }
    }
    @media (min-width: 641px) { .demo-pill .narrow { display: none; } }`;
  document.head.appendChild(css);
  document.body.classList.add('demo-on');
  const veil = Object.assign(document.createElement('div'), {className: 'demo-veil', textContent: 'Resetting the demo flat...'});
  const veilOn = text => { veil.textContent = text; veil.classList.add('on'); };
  const toasts = Object.assign(document.createElement('div'), {className: 'demo-toasts'});
  const cover = Object.assign(document.createElement('div'), {className: 'demo-wait'});    // out of turn: never the house
  cover.setAttribute('role', 'dialog'); cover.setAttribute('aria-live', 'polite');
  document.body.append(veil, toasts, cover);

  // ---- what the demo refuses: greyed or hidden before any press ----
  let GREY = [];
  fetch('/plugins/demo/static/greyed.json').then(r => r.json()).then(d => { GREY = d.controls || []; applyGrey(); }).catch(() => {});
  function applyGrey(root) {
    for (const g of GREY) {
      (root || document).querySelectorAll(g.sel).forEach(el => {
        if (g.text && el.textContent.trim() !== g.text) return;
        if (el.dataset.demoOff) return;
        el.dataset.demoOff = '1';
        if (g.do === 'hide') { el.style.setProperty('display', 'none', 'important'); return; }
        el.classList.add('demo-off');
        el.onclick = null;                         // an inline handler of the page (the gear's) runs no more
        el.title = NA;
        el.setAttribute('aria-disabled', 'true');
        el.addEventListener('click', ev => { ev.preventDefault(); ev.stopImmediatePropagation(); toast(NA); }, true);
      });
    }
  }
  new MutationObserver(() => applyGrey()).observe(document.body, {childList: true, subtree: true});

  // ---- Settings in the demo: every page with what it does and why a house needs it ----
  // The engine itself greys a page whose routes the demo refuses ("Not available here"); this box says what the page
  // is for in a real house, so a guest learns the whole system even where the demo cannot run it.
  const TRY = 'Try it: changes here are real for this turn and go back at the reset.';
  const LOOK = 'In the demo: shown to read; it needs the real house (its network, servers or hardware).';
  const WHY = {
    overview: ['The house checks itself every few minutes: devices that stopped answering, low batteries, a full disk, a failed backup, certificates and services.',
      'You open one page and see whether anything needs you, instead of finding out when a light does not switch.', LOOK],
    rooms: ['The plan of the flat: rooms, their names and which thermometer speaks for each room.',
      'Rules, voice and the map all speak in rooms ("turn off the bedroom"), so the house has to know where everything is.', TRY],
    family: ['The people of the house, their phones and what each may do; the phone app pairs here.',
      'Presence (who is home), notifications and rights (a child cannot open the gate) all hang on it.', LOOK],
    weather: ['Where the forecast and the current weather come from: an online source or the house\'s own station.',
      'Heating, blinds and watering rules use it, and the panels show it.', LOOK],
    devices: ['Every device of the house in one list: what it is, how it is connected, which room it is in and whether it answers.',
      'The one place to find a device, move it to another room or see why it is silent.', TRY],
    zigbee: ['The Zigbee radio network: the gateway, every Zigbee device, its link quality, battery and pairing of new ones.',
      'Most sensors and switches are Zigbee: cheap, battery-powered and local, no cloud. This is where they join the house.',
      'In the demo: the devices are listed; pairing and the gateway need the real radio.'],
    ir: ['Infrared blasters and the remotes they learned: air conditioners, TVs, fans without a network.',
      'Old appliances join the house: a rule or a voice command presses their remote for you.', TRY],
    tv: ['Every TV: its address, pairing, inputs and apps.', 'The house turns a TV on, switches its input and starts a film or an app.', TRY],
    panels: ['Wall panels and tablets: their screens are laid out here (the builder), bound to rooms and given firmware.',
      'A panel by the door or in the kitchen is the house\'s remote for everyone, no phone needed.',
      'In the demo: layouts can be looked at and changed; pairing and firmware need a real panel.'],
    nfc: ['NFC tags and cards: what each one starts when a phone or a reader touches it.', 'A tag by the bed says "good night"; a card at the door opens it.', LOOK],
    computers: ['The computers of the house and the servers on them: firmware and app builds, speech, the big language model, the touchpad receivers. One broadcast finds which runs where.',
      'Heavy work goes to the strongest computer; the house itself stays small and quiet.', LOOK],
    rules: ['What happens when: a button, a sensor, a time or the sun starts actions on devices.',
      'This is the "smart" in a smart home: lights that follow you, heating that knows you are out, an alarm on a leak.', TRY],
    history: ['Everything that happened in the house and who did it: a person, a rule, a schedule, a voice command.',
      'When something switched by itself, history tells you why.', TRY],
    watchdog: ['The house\'s self-repair: what it restarts by itself, and when it forgets a device that is gone for good.',
      'Small faults heal at night without you; you only hear about what it could not fix.', LOOK],
    voice: ['The wake word, the answers and the satellites (microphones in the rooms).', 'Hands-free control, all on the house\'s own servers: no cloud listens.', LOOK],
    lang: ['The language of the house (names, voice, panels) and of this screen.', 'Every family member may read the house in their own language.',
      'In the demo: the demo speaks English only.'],
    device: ['How this screen is signed in, and the app shortcut for its home screen.', 'Each screen has its own key; one lost tablet is cut off alone.', LOOK],
    signin: ['Let another phone, tablet or computer of the home network in, with a short code.', 'No passwords to type on a wall panel or a TV.', LOOK],
    backups: ['Nightly archives of all the house\'s settings and data, and downloads of them.', 'A dead disk or a wrong change costs a minute, not a weekend.', LOOK],
    plugins: ['What is switched on (every part of the house is a plug-in) and new versions of the house.', 'The house grows by switching parts on, and updates itself safely.', LOOK],
    restart: ['Starts every service of the house anew.', 'The last resort when something stays stuck; the house comes back by itself in a minute.', LOOK],
    fwgen: ['yashGen: builds the firmware for the house\'s own ESP sensors and switches from a few clicks.', 'Home-made devices without writing code.', LOOK],
  };
  // every control of a Settings page that has a hint in the house's help (the "?" of the header) shows it under itself
  let hintQueued = false;
  function drawHints() {
    hintQueued = false;
    const body = document.querySelector('#stx:not([hidden]) .stx-body');
    const entries = Home.help && typeof Home.help.entries === 'function' ? Home.help.entries() : [];
    if (!body) return;
    for (const e of entries) {
      if (!e.sel || !e.text) continue;
      let el;
      try { el = [...body.querySelectorAll(e.sel)].find(x => x.getClientRects().length); } catch (err) { continue; }
      if (!el || el.closest('svg, .demo-why, .demo-items')) continue;
      if (el.closest('.stx-tabs')) continue;                     // the page's tabs: the box above says what they are
      if (body.querySelector(`.demo-hint[data-h="${CSS.escape(e.id)}"]`)) continue;
      const text = `<b>${E(i18n(e.title || ''))}:</b> ${E(i18n(e.text))}`;
      // a row of a settings list: the hint under that row; anything else (a toolbar, a group of buttons, the map's bar):
      // a line of "On this page" in the box above, so the page's own layout never moves
      const row = el.closest('.row');
      const flat = row && row.parentElement && !/flex|grid/.test(getComputedStyle(row.parentElement).display);
      const h = Object.assign(document.createElement('div'), {className: 'demo-hint'});
      h.dataset.h = e.id;
      h.innerHTML = text;
      if (flat) {
        let at = row;
        while (at.nextElementSibling?.classList.contains('demo-hint')) at = at.nextElementSibling;
        at.after(h);
        continue;
      }
      const why = body.querySelector(':scope > .demo-why');
      if (!why) continue;
      let list = why.querySelector('.demo-onpage');
      if (!list) {
        list = Object.assign(document.createElement('div'), {className: 'demo-onpage'});
        list.innerHTML = '<p><b>On this page:</b></p>';
        why.append(list);
      }
      list.append(h);
    }
  }
  const queueHints = () => { if (!hintQueued) { hintQueued = true; requestAnimationFrame(drawHints); } };

  // the plug-ins this demo keeps off still get their Settings page: each of its items, what it is and why
  const OFF = 'Not in this demo: it needs the real house. Here is what the page holds there.';
  const SHOW = {
    computers: [['Computers', [
      ['The card of a computer', 'Whether the house reaches it (its key logs in, sudo asks no password), its name, and which TV and input its screen is: read from the screen\'s EDID, so "the PC on the LG, HDMI 3" is known by itself.'],
      ['Search the network / Add by address', 'Finds the house\'s other computers, or takes one by hand. The house logs in with its own key only.'],
      ['One broadcast: who runs what', 'Every computer answers a single question of the house with the servers it runs, so a new receiver or player appears without typing an address.'],
    ]], ['Servers', [
      ['Build server', 'Compiles the firmware of the house\'s own ESP sensors, switches and wall panels. Heavy work, so it runs on the strongest computer, not on the house.'],
      ['Android app builder', 'Builds the house\'s phone app and the wall-panel launcher with the house\'s own address and keys inside: no app store.'],
      ['Speech (TTS)', 'Turns the house\'s answers into a voice for the satellites and panels, on a computer of the house: nothing goes to the cloud.'],
      ['Big model (LLM)', 'A local language model answers free questions ("is the washing done?") and turns sentences into commands. It wants a GPU, so it lives on the gaming PC.'],
      ['yashGen firmware builder', 'Makes the firmware of a new home-made device from a few clicks: pick the board and the parts, get a working device.'],
      ['Player', 'mpv on the computer at a TV: the house turns the TV on, picks the input and plays a film, with Continue and the next episode.'],
      ['Touchmouse receiver', 'Lets a phone or a wall panel be the touchpad and keyboard of that computer: pointer, clicks, scrolling, media keys and typed text.'],
    ]]],
    touchmouse: [['Touchmouse', [
      ['What it is', 'A phone (the Yash! app) or a wall panel becomes a touchpad for a TV box or a computer at a TV: no wireless mouse on the sofa.'],
      ['Receivers', 'Each computer or TV box that takes it runs a small receiver. Computers of the house get it from their card, and the house finds them by itself; a TV box can be added by address.'],
      ['Pad and buttons', 'Move, tap to click, two fingers to scroll; a row of back, play/pause, forward and volume, plus arrows and Enter for TV menus.'],
      ['Typing', 'Text typed on the phone appears on the computer, any language: search a film without a keyboard.'],
      ['Safety', 'It works only inside the home network and the house\'s VPN; nothing of it reaches the internet.'],
    ]]],
    family: [['Family', [
      ['Members', 'Each person of the house with a name, a photo and a phone.'],
      ['The phone app', 'Pairs a phone with the house: controls, notifications, the touchpad, films; it updates itself from the house.'],
      ['Rights', 'What each one may do: a child switches the lights but not the gate.'],
      ['Presence', 'Who is home, from the phones: rules can heat up before you arrive and switch everything off when the last one leaves.'],
    ]]],
    weather: [['Weather', [
      ['Source', 'Where the forecast comes from: an online service, or the house\'s own weather station.'],
      ['Uses', 'Panels and clocks show it; rules close the blinds in a heatwave, skip watering when rain comes.'],
    ]]],
    nfc: [['NFC tags', [
      ['Tags', 'Stickers and cards: touch one with a phone and the house does something.'],
      ['Add by tapping', 'Press Add, touch the new tag with any family phone: it is in the house, ready for a rule.'],
      ['Rules', '"A tag was tapped" starts any rule: a tag at the bed says good night, a card at the door opens it.'],
    ]]],
    voice: [['Voice', [
      ['Wake word', 'The word that wakes the house; everything before it stays on the satellite.'],
      ['Satellites', 'Small microphones and speakers in the rooms; they know their room, so "turn off the light" means this room.'],
      ['Answers', 'Spoken by the house\'s own speech server; free questions go to the local big model.'],
    ]]],
    fwgen: [['yashGen', [
      ['The builder', 'Pick a board and parts (sensors, relays, a screen) and get firmware for a home-made device, flashed over the network.'],
      ['Why', 'Cheap ESP boards become exactly the device the house needs, with no code written by hand.'],
    ]]],
  };
  function showcase(subject) {
    return box => {
      box.innerHTML = `<div class="demo-items"><div class="demo-why"><p class="dm">${E(OFF)}</p></div>${
        SHOW[subject].map(([h, items]) => `<h3>${E(h)}</h3>` + items.map(([t, x]) => `<div class="demo-item"><b>${E(t)}</b><span>${E(x)}</span></div>`).join('')).join('')}</div>`;
    };
  }
  const SHOW_AT = {computers: 'computers', touchmouse: 'computers', family: 'family', weather: 'weather', nfc: 'nfc', voice: 'voice', fwgen: 'fwgen'};
  const showSettings = Object.keys(SHOW)          // all of them are off here (compose.demo.yml PLUGINS; a test checks)
    .map(k => ({subject: SHOW_AT[k], title: SHOW[k][0][0] === 'Computers' ? 'Computers and servers' : SHOW[k][0][0], render: showcase(k)}));

  function stPageId() {             // the page drawn (a link to a page that is not here opens another one)
    if (typeof ST !== 'undefined' && ST.page) return ST.page;
    const m = location.hash.match(/^#settings(?:\/([^/]+))?/);
    return m && m[1] ? decodeURIComponent(m[1]) : '';
  }
  function drawWhy() {
    const body = document.querySelector('#stx:not([hidden]) .stx-body');
    if (!body) return;
    const id = stPageId(), w = WHY[id];
    const old = body.querySelector(':scope > .demo-why');
    if (old && old.dataset.page === id && body.firstElementChild === old) return;
    old?.remove();
    if (!w) return;
    const box = Object.assign(document.createElement('div'), {className: 'demo-why'});
    box.dataset.page = id;
    box.innerHTML = `<p><b>What it does.</b> ${E(w[0])}</p><p><b>Why a house needs it.</b> ${E(w[1])}</p><p class="dm">${E(w[2])}</p>`;
    body.prepend(box);
  }
  new MutationObserver(() => { drawWhy(); queueHints(); }).observe(document.body, {childList: true, subtree: true});
  addEventListener('hashchange', () => setTimeout(drawWhy, 0));

  function toast(html, ms) {
    const t = document.createElement('div');
    t.className = 'demo-toast';
    t.innerHTML = html;
    toasts.appendChild(t);
    while (toasts.children.length > 3) toasts.firstChild.remove();
    setTimeout(() => t.remove(), ms || 5000);
  }

  // ---- the header pill and the narrow-screen menu ----
  function drawPill() {
    if (!pill || !st) return;
    const msg = Date.now() < noteUntil ? ` <span class="tag">${E(note)}</span>` : '';
    let h;
    if (!control()) { pill.innerHTML = ''; return; }        // out of turn the cover shows the wait
    if (st.idle_s < 60 && st.idle_s < st.left_s) {         // nothing pressed for a while: the turn ends at 0
      h = `<span class="tag" style="background:#6b4a10">Still there? <b>${E(mmss(st.idle_s))}</b></span>
           <button data-a="stay" class="main">Yes</button><button data-a="release">Release</button>`;
    } else {
      h = `<span class="tag ctl">You are in control <b>${E(mmss(Math.min(st.left_s, st.idle_s)))}</b></span>
           ${st.can_reset ? '<button data-a="reset" class="wide">Reset</button>' : ''}<button data-a="release">Release</button>`;
    }
    const replay = `<button data-a="intro" class="replay" title="Replay the intro" aria-label="Replay the intro"><svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path d="M4 12a8 8 0 1 0 2.4-5.7M4 4v4h4" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/><path d="M10 9v6l5-3z" fill="currentColor"/></svg>&#8203;<span class="wide">Intro</span></button>`;           // the zero-width space: a text line, so the height of the pill's other buttons
    pill.innerHTML = `<span class="demo-pill">${replay}${h}${msg}<button data-a="menu" class="narrow" aria-label="Menu">${Home.icon('more', 16)}</button></span>`;
    pill.querySelectorAll('button').forEach(b => { b.onclick = ev => { ev.stopPropagation(); act(b.dataset.a); }; });
  }

  function menu() {
    document.querySelector('.demo-menu')?.remove();
    const m = Object.assign(document.createElement('div'), {className: 'demo-menu'});
    const items = [];
    const hidden = [...document.querySelectorAll('.demo-hide-narrow button, .demo-hide-narrow')].filter(b => b.tagName === 'BUTTON');
    hidden.forEach(b => items.push([b.textContent.trim(), () => b.click()]));
    if (control() && st.can_reset) items.push(['Reset the flat', () => act('reset')]);
    items.push(['Settings', () => openSettings()]);
    m.innerHTML = items.map((it, i) => `<button data-i="${i}">${E(it[0])}</button>`).join('');
    m.querySelectorAll('button').forEach(b => { b.onclick = () => { m.remove(); items[+b.dataset.i][1](); }; });
    document.body.appendChild(m);
    setTimeout(() => document.addEventListener('click', () => m.remove(), {once: true}), 0);
  }

  function markHeader() {             // History and Health go into the menu on a narrow screen
    document.querySelectorAll('header button, header .plugslot > *').forEach(b => {
      if (/^(History|Health)/.test((b.textContent || '').trim()) && !b.closest('.demo-pill')) b.classList.add('demo-hide-narrow');
    });
  }

  async function act(a) {
    if (a === 'menu') return menu();
    if (a === 'intro') return intro();
    if (a === 'stay') a = 'still';
    if (a === 'reset' && !confirm('Reset the flat to its start? Everything changed in this turn goes back.')) return;
    try {
      if (a === 'logout') {
        await Home.api('/api/demo/logout', {method: 'POST'}).catch(() => {});
        localStorage.removeItem('hs_token');
        return location.replace('/try');
      }
      st = await Home.api(`/api/demo/${a}`, {method: 'POST'});
      if (a === 'reset') veilOn('Resetting the demo flat...');
      roleSeen();
    } catch (e) {
      note = why(e); noteUntil = Date.now() + 6000;
      if (control()) toast(E(note));                 // out of turn the cover says it
    }
    drawPill(); drawSim(); drawCover();
  }

  // a refused press always says why
  function why(e) {
    if (e && e.status === 429 && !e.detail) return 'Too many presses at once: wait a second and try again';
    return (e && (e.detail || e.message)) || String(e);
  }

  const notYours = () => toast('Your turn is over: the flat is not yours now.');
  const ENDED = {'tab closed': 'the page was in the background for over 30 s', idle: 'nothing was pressed for 3 minutes',
                 'time is up': 'the 15 minutes were up', released: 'you released it', 'signed out': 'you signed out'};

  function roleSeen() {                              // after every answer that carries the role
    drawCover();
    if (!st || lastRole === st.role) return;
    if (lastRole) Home.refresh();
    const was = lastRole;
    lastRole = st.role;
    document.body.classList.toggle('demo-ctl', st.role === 'control');
    window.dispatchEvent(new Event('restricted-role'));        // the map: edit or not, from the first answer on
    if (control()) {
      if (was) { toast('<b>Your turn.</b> The flat is yours for up to 15 min.', 7000); Home.openTab('p:map'); markBar(); }
      if (ready) firstLook();
    }
  }

  // ---- out of turn: a page of its own over the house (the wait, or the summary of the turn that ended) ----
  let coverHtml = '';
  function drawCover() {
    const on = !control();
    if (document.body.classList.contains('demo-waiting') !== on) {
      document.body.classList.toggle('demo-waiting', on);
      document.querySelectorAll('body > :not(.demo-wait)').forEach(el => { el.inert = on; });     // no key reaches the house
    }
    if (!on) return;
    const err = Date.now() < noteUntil ? `<p class="err">${E(note)}</p>` : '';
    const btn = (a, label, main) => `<button class="demo-btn${main ? ' main' : ''}" data-a="${a}">${E(label)}</button>`;
    let h;
    if (!st) h = '<h1>Yashome demo</h1><p class="demo-dim">Connecting...</p>';
    else if (st.position) {
      const wait = st.eta_s < 60 ? 'Free in under a minute' : `Free in about ${Math.ceil(st.eta_s / 60)} min`;
      h = `<h1>${st.busy ? 'Demo is busy' : 'The flat is being reset'}</h1><p class="big">${E(wait)}</p>
        <p>You are #${st.position} in line. Keep this page open: the demo opens by itself when your turn comes.</p>
        <p class="demo-dim">One guest at a time, up to 15 min each.</p>${err}<div class="demo-row">${btn('leave', 'Leave the line')}</div>`;
    } else if (st.summary) {
      const s = st.summary, fb = window.__demoFeedback ? `<p><a href="${E(window.__demoFeedback)}" target="_blank" rel="noopener">Tell us what you think</a></p>` : '';
      h = `<h1>Thanks for trying Yashome</h1><p class="demo-dim">Your turn ended: ${E(ENDED[s.why] || s.why || 'it is over')}.</p>
        <p>${E(s.minutes)} min in control, ${E(plural(s.actions, 'action'))}, ${E(plural(s.rules, 'rule'))} fired, ${done.size} of ${TASKS.length} things tried.</p>
        <p class="demo-dim">The flat goes back to its start for the next guest.</p>${fb}${err}
        <div class="demo-row">${btn('take', 'Get in line again', true)}${btn('logout', 'Sign out')}</div>`;
    } else {
      h = `<h1>You are not in line</h1><p class="demo-dim">Your place was given up: the page was closed or left the line.</p>${err}
        <div class="demo-row">${btn('take', 'Get in line', true)}${btn('logout', 'Sign out')}</div>`;
    }
    if (h === coverHtml) return;
    coverHtml = h;
    cover.innerHTML = `<div class="card">${h}</div>`;
    cover.querySelectorAll('button').forEach(b => { b.onclick = () => act(b.dataset.a); });
  }

  async function beat() {
    try {
      st = await Home.api('/api/demo/heartbeat', {method: 'POST'});
      fails = 0;
      veil.classList.remove('on');
      roleSeen();
    } catch (e) {
      if (++fails >= 2) veilOn('Reconnecting to the demo...');      // a reset restarts the backend; a banner, never a block
    }
    markHeader(); drawPill(); drawSim();
  }

  // ---- things to try: live controls of the flat (the same calls as a card or the sections below); the check means tried ----
  const val = (id, code) => ((Home.state(id) || {}).values || {})[code];
  const isOn = v => v === true || v === 'ON' || v === 'on';
  const alexIn = () => (sim.residents || {}).Alex === 'bath';
  const simPost = (a, body) => Home.api(`/api/demo/sim/${a}`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  const send = async (dev, code, value) => { if (!await Home.sendControl(dev, code, value)) throw new Error('The house refused it'); };
  const TASKS = [
    {id: 'light', kind: 'switch', text: 'Living room ceiling light', see: 'The lamp lights up on the plan.', hl: ['Living room ceiling'],
     get: () => isOn(val('Living room ceiling', 'state')), set: v => send('Living room ceiling', 'state', v), did: v => `Living room ceiling ${v ? 'on' : 'off'}`},
    {id: 'ac', kind: 'ac', text: 'Bedroom AC', see: 'Cool or heat to the degrees set; the room follows over the next minutes.', hl: ['bedroom_ac']},
    {id: 'lock', kind: 'lock', text: 'Front door', see: 'The lock on the plan shows it; a rule tells the hallway.', hl: ['front_lock'],
     get: () => ![false, 'UNLOCKED', 'unlocked'].includes(val('front_lock', 'locked')), set: v => send('front_lock', 'locked', v),
     did: v => `Front door ${v ? 'locked' : 'unlocked'}`},
    {id: 'window', kind: 'window', text: 'Living room window', see: 'Opened with the AC on, a rule switches the AC off.', hl: ['Living room window', 'living_ac'],
     get: () => val('Living room window', 'contact') === false, set: v => simPost('event', {name: v ? 'window_open' : 'window_close'}),
     did: v => `Living room window ${v ? 'open' : 'closed'}`},
    {id: 'bell', kind: 'press', text: 'Doorbell', see: 'A rule switches the hallway light on.', hl: ['Doorbell'],
     label: () => 'Ring', set: () => simPost('event', {name: 'doorbell'}), did: () => 'Doorbell rang'},
    {id: 'move', kind: 'press', text: 'Alex: the bathroom and back', see: 'The radar sees Alex; a rule switches the light on, then off.', hl: ['bathroom_radar'],
     label: () => alexIn() ? 'Back' : 'Send', set: () => simPost('move', {who: 'Alex', room: alexIn() ? 'living' : 'bath'}),
     did: () => alexIn() ? 'Alex went back to the living room' : 'Alex went to the bathroom'},
    {id: 'drag', kind: 'note', text: 'Drag a device to a new place', hl: [],
     see: 'On the plan, as the owner does: rename it, add a room, wire it. All of it goes back at the reset.'},
  ];
  const AC = 'bedroom_ac', AC_MODES = {                     // the AC's two modes as icons: a snowflake, a sun
    cool: '<path d="M12 2v20M4 6l16 12M20 6 4 18M9 3l3 3 3-3M9 21l3-3 3 3" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
    heat: '<circle cx="12" cy="12" r="4.5" fill="currentColor"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'};
  let expect = null;                              // a change waits a few seconds for the rules that follow it
  async function actTask(t, run, did) {
    if (!control()) return notYours();
    if ((Home.activeTab ? Home.activeTab() : '') !== 'p:map') Home.openTab('p:map');
    if (!wide()) sheet(SNAP.peek);                  // a phone: the sheet steps aside so the plan shows what happens
    try { await run(); }
    catch (e) { toast(E(why(e))); return; }
    if (!done.has(t.id)) { done.add(t.id); sessionStorage.setItem('demo-done', JSON.stringify([...done])); }
    expect = {did, until: Date.now() + 6000};
    toast(`<b>${E(did)}</b>`, 4000);
    setTimeout(() => t.hl.forEach(highlight), 300);
    if (!wide() && window.MapView) mapIds(t.hl, true).then(ids => { if (ids.length) MapView.zoomTo(ids); });   // a phone: the plan shows the room
    setTimeout(poll, 900); setTimeout(poll, 2500);
    drawTasks();
  }
  function taskControl(t) {                       // the row's control, drawn once; drawTasks() keeps it to the flat's state
    const sw = (a, label) => `<div class="toggle setting" role="switch" tabindex="0" data-a="${a}" aria-label="${E(label)}"></div>`;
    if (t.kind === 'switch') return sw('sw', t.text);
    if (t.kind === 'lock' || t.kind === 'window') return `<button class="demo-btn tstate" data-a="flip"></button>`;
    if (t.kind === 'press') return `<button class="demo-btn main" data-a="press"></button>`;
    if (t.kind === 'note') return '';                    // a thing to try on the plan itself
    return `<span class="tac">${sw('acpow', 'Bedroom AC power')}${Object.entries(AC_MODES).map(([m, p]) => `<button class="demo-btn tmode" data-a="m-${m}" aria-label="${m === 'cool' ? 'Cool' : 'Heat'}" title="${m === 'cool' ? 'Cool' : 'Heat'}" aria-pressed="false"><svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">${p}</svg></button>`).join('')}
      <button class="demo-btn" data-a="tdown" aria-label="Cooler">-</button><b data-a="temp"></b><button class="demo-btn" data-a="tup" aria-label="Warmer">+</button></span>`;
  }
  function bindTask(row, t) {
    const q = a => row.querySelector(`[data-a="${a}"]`), key = (el, f) => { el.onclick = f; el.onkeydown = ev => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); f(); } }; };
    if (t.kind === 'switch') key(q('sw'), () => { const v = !t.get(); actTask(t, () => t.set(v), t.did(v)); });
    if (t.kind === 'lock' || t.kind === 'window') q('flip').onclick = () => { const v = !t.get(); actTask(t, () => t.set(v), t.did(v)); };
    if (t.kind === 'press') q('press').onclick = () => { const d = t.did(); actTask(t, t.set, d); };
    if (t.kind !== 'ac') return;
    key(q('acpow'), () => { const v = !isOn(val(AC, 'power')); actTask(t, () => send(AC, 'power', v), `Bedroom AC ${v ? 'on' : 'off'}`); });
    for (const m of Object.keys(AC_MODES)) q('m-' + m).onclick = () => actTask(t, () => send(AC, 'mode', m), `Bedroom AC: ${m}`);
    const deg = d => { const v = Math.max(16, Math.min(30, (+val(AC, 'temp') || 23) + d)); actTask(t, () => send(AC, 'temp', String(v)), `Bedroom AC set to ${v} degrees`); };
    q('tdown').onclick = () => deg(-1); q('tup').onclick = () => deg(1);
  }
  function drawTasks() {                          // after every state frame: each control shows the flat as it is now
    const box = simBox;
    if (!box) return;
    const can = control();
    for (const t of TASKS) {
      const row = box.querySelector(`.demo-task[data-t="${t.id}"]`);
      if (!row) continue;
      const q = a => row.querySelector(`[data-a="${a}"]`);
      const tog = (el, on) => { el.classList.toggle('on', on); el.setAttribute('aria-checked', String(on)); el.setAttribute('aria-disabled', String(!can)); el.classList.toggle('off', !can); };
      const txt = (el, h) => { if (el && el.innerHTML !== h) el.innerHTML = h; };
      if (t.kind === 'switch') tog(q('sw'), t.get());
      if (t.kind === 'lock') { const v = t.get(); txt(q('flip'), `${Home.icon(v ? 'lock' : 'unlock', 14)} ${v ? 'Locked' : 'Unlocked'}`); q('flip').setAttribute('aria-pressed', String(v)); }
      if (t.kind === 'window') { const v = t.get(); txt(q('flip'), v ? 'Open' : 'Closed'); q('flip').setAttribute('aria-pressed', String(v)); }
      if (t.kind === 'press') txt(q('press'), E(t.label()));
      if (t.kind === 'ac') {
        tog(q('acpow'), isOn(val(AC, 'power')));
        const m = val(AC, 'mode');
        for (const k of Object.keys(AC_MODES)) { const b = q('m-' + k); b.classList.toggle('sel', m === k); b.setAttribute('aria-pressed', String(m === k)); }
        txt(q('temp'), `${E(val(AC, 'temp') ?? '-')}&deg;`);
        q('tdown').disabled = q('tup').disabled = !can;
      }
      row.querySelectorAll('button').forEach(b => { b.disabled = !can; });
      const ok = done.has(t.id), ck = row.querySelector('.ck');
      row.classList.toggle('ok', ok);
      if (ck.dataset.ok !== String(ok)) { ck.dataset.ok = String(ok); ck.innerHTML = ok ? Home.icon('check', 13) : ''; }      // drawn: a typed check mark may be missing from the font
    }
  }

  // ---- the feed: toasts and map highlights when the house acts on its own ----
  async function poll() {
    try {
      const d = await Home.api(`/api/demo/feed?after=${after}`);
      window.__demoFeedback = d.feedback || '';
      if (d.seq < after) after = 0;               // the backend started again (a reset)
      for (const f of d.items) {
        feed.push(f);
        if (f.who === 'rule' && after) {
          const then = expect && Date.now() < expect.until;
          toast(then ? `${E(expect.did)} &rarr; <b>${E(f.text.split(' -> ').pop())}</b> (rule)` : `<b>Rule fired:</b> ${E(f.text)}`, then ? 7000 : 5000);
          highlight(f.device); highlight(f.src);
        }
      }
      if (feed.length > 100) feed = feed.slice(-100);
      after = d.seq;
    } catch (e) { /* signed out or resetting */ }
    try { sim = await Home.api('/api/demo/sim'); } catch (e) { /* the same */ }
    drawSim();
  }

  let mapRoom = {};                                // an icon's room, for a view of the whole room
  async function mapIds(devs, rooms) {            // the plan's icons of these devices (and the lamps they switch); rooms: all of their rooms
    if (!mapIdx) {
      try {
        const m = await Home.api('/api/map');
        mapIdx = {};
        for (const it of m.items || []) { if (it.kind === 'device') (mapIdx[it.dev] = mapIdx[it.dev] || []).push(it.id); mapRoom[it.id] = it.room || ''; }
        for (const l of m.links || []) (mapIdx[l.dev] = mapIdx[l.dev] || []).push(l.load);
      } catch (e) { return []; }
    }
    const ids = devs.flatMap(d => mapIdx[d] || []), rs = new Set(ids.map(i => mapRoom[i]).filter(Boolean));
    return rooms && rs.size ? Object.keys(mapRoom).filter(i => rs.has(mapRoom[i])) : ids;
  }
  async function highlight(dev) {
    if (!dev) return;
    for (const id of await mapIds([dev])) {
      const el = document.querySelector(`[data-id="${CSS.escape(id)}"]`);
      if (!el) continue;
      el.classList.remove('demo-hl'); void el.offsetWidth; el.classList.add('demo-hl');
      setTimeout(() => el.classList.remove('demo-hl'), 3200);
    }
  }

  // ---- the Simulate tab: built once, then updated in place (a button under a finger is never replaced) ----
  const EVENTS = [['doorbell', 'Ring the doorbell'], ['window_open', 'Open the living room window'], ['window_close', 'Close it'],
    ['leak', 'Water leak in the kitchen'], ['leak_dry', 'Dry it'], ['smoke', 'Smoke in the kitchen'], ['smoke_clear', 'Clear it']];
  function buildSim(box) {
    const b = (a, v, label) => `<button class="demo-btn" data-s="${a}" data-v="${E(v)}">${E(label)}</button>`;
    box.innerHTML = `<div class="demo-panel">
      <p data-x="status"></p>
      <h3>Things to try</h3>${TASKS.map(t => `<div class="demo-task" data-t="${t.id}"><span class="txt">${E(t.text)}<span class="see">${E(t.see)}</span></span>
        ${taskControl(t)}<span class="ck" title="Tried"></span></div>`).join('')}
      <h3>Wall panel</h3><div class="demo-row"><button class="demo-btn" data-x="float">See the tablet</button><a class="demo-btn" href="/panel-builder?panel=playground" target="_blank" rel="noopener">Shape it in the builder</a></div>
      <h3>Time</h3><div class="demo-row">${[1, 10, 60].map(x => b('speed', x, `x${x}`)).join('')}</div>
      <h3>Weather <span class="demo-dim" data-x="held"></span></h3><div class="demo-row">${['clear', 'cloudy', 'rain', 'heatwave'].map(w => b('weather', w, w)).join('')}${b('weather', 'auto', 'Back to normal')}</div>
      <h3>Events</h3><div class="demo-row" data-sec="events">${EVENTS.map(e => b('event', e[0], e[1])).join('')}</div>
      <h3>Residents</h3><div data-sec="residents">${['Alex', 'Sam', 'Mia'].map(r => `<div class="demo-row" style="margin:4px 0"><b style="min-width:48px">${r}</b>
        <span class="demo-dim" style="min-width:90px" data-where="${r}"></span>
        ${Object.entries(ROOMS).map(([k, n]) => b('move', `${r}=${k}`, n)).join('')}${b('move', `${r}=`, 'Out')}</div>`).join('')}</div>
      <h3>What happened</h3><div class="demo-feed" data-x="feed"></div>
    </div>`;
    TASKS.forEach(t => bindTask(box.querySelector(`.demo-task[data-t="${t.id}"]`), t));
    box.querySelector('[data-x="float"]').onclick = () => {        // over the map: press on the tablet, watch the flat react
      if (window.PanelFloat) { if (!wide()) sheet(SNAP.peek); PanelFloat.open('playground'); }
      else open('/panel-view.html?panel=playground', '_blank', 'noopener');
    };
    box.querySelectorAll('[data-s]').forEach(el => {
      el.onclick = async () => {
        if (!control()) return notYours();
        const a = el.dataset.s, v = el.dataset.v;
        const body = a === 'speed' ? {x: +v} : a === 'weather' ? {mode: v} : a === 'event' ? {name: v}
          : {who: v.split('=')[0], room: v.split('=')[1] || null};
        el.classList.add('sel');
        try { await Home.api(`/api/demo/sim/${a}`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)}); }
        catch (e) { toast(E(why(e))); }
        setTimeout(poll, 400);
      };
    });
  }

  function drawSim() {
    const box = simBox;
    if (!box || !box.isConnected) return;
    if (!box.querySelector('[data-x=status]')) buildSim(box);
    const can = control(), res = sim.residents || {};
    const set = (sel, text) => { const el = box.querySelector(sel); if (el && el.textContent !== text) el.textContent = text; };
    const sd = side.querySelector('.shead .demo-dim'), sdt = can ? 'you are in control' : '';
    if (sd.textContent !== sdt) sd.textContent = sdt;
    set('[data-x=status]', `Flat time ${sim.time || '--:--'} \u00b7 outside ${sim.outdoor ?? '-'}\u00b0 \u00b7 ${sim.weather || ''}`);
    set('[data-x=held]', sim.held_until ? `(yours until ${sim.held_until})` : '(the day\'s own)');
    box.querySelectorAll('[data-s]').forEach(el => {
      const a = el.dataset.s, v = el.dataset.v;
      const sel = a === 'speed' ? sim.speed === +v : a === 'weather' ? (v === 'auto' ? !sim.held_until : sim.held_until && sim.weather === v)
        : a === 'move' ? (res[v.split('=')[0]] || '') === (v.split('=')[1] || '') : false;
      if (a !== 'event') el.classList.toggle('sel', sel);
      el.classList.toggle('off', !can);
      if (can) el.removeAttribute('aria-disabled');
      else el.setAttribute('aria-disabled', 'true');
    });
    drawTasks();
    box.querySelectorAll('[data-where]').forEach(el => { const w = res[el.dataset.where]; const t = w ? ROOMS[w] : 'out'; if (el.textContent !== t) el.textContent = t; });
    const html = feed.slice(-15).reverse().map(f => `<div><span class="demo-dim">${new Date(f.ts * 1000).toTimeString().slice(0, 5)}</span> ${f.who === 'rule' ? '<b>rule</b>' : 'you'} - ${E(f.text)}${f.n > 1 ? ` <span class="demo-dim">x${f.n}</span>` : ''}</div>`).join('') || '<span class="demo-dim">Nothing yet.</span>';
    const fd = box.querySelector('[data-x=feed]');
    if (fd && fd.innerHTML !== html) fd.innerHTML = html;
  }

  // ---- Ask the house (the header's field): no language model in the demo; example questions answered from the flat now ----
  const LIGHT = /light|ceiling|lamp|strip/i;
  const lights = () => Home.devices().filter(d => LIGHT.test(d.id + ' ' + (d.name || '')) && (d.controls || []).some(c => c.code === 'state'));
  const nameOf = d => d.name || d.id;
  const list = xs => xs.length < 2 ? xs.join('') : xs.slice(0, -1).join(', ') + ' and ' + xs[xs.length - 1];
  const ASK = [
    ['Is anyone home?', async () => {
      const res = sim.residents || {}, here = Object.entries(res).filter(([, r]) => r), out = Object.keys(res).filter(k => !res[k]);
      if (!here.length) return 'Nobody is home right now.';
      return list(here.map(([w, r]) => `${w} is in the ${(ROOMS[r] || r).toLowerCase()}`)) + (out.length ? `; ${list(out)} ${out.length > 1 ? 'are' : 'is'} out.` : '.');
    }],
    ['How warm is the bedroom?', async () => {
      const t = val('Bedroom climate', 'temperature'), h = val('Bedroom climate', 'humidity');
      return t == null ? 'The bedroom sensor has not reported yet.' : `${(+t).toFixed(1)} degrees in the bedroom${h != null ? `, humidity ${Math.round(h)} %` : ''}.`;
    }],
    ['Which lights are on?', async () => {
      const on = lights().filter(d => isOn(val(d.id, 'state'))).map(nameOf);
      return on.length ? `On now: ${list(on)}.` : 'All the lights are off.';
    }],
    ['Turn off all the lights', async () => {
      const on = lights().filter(d => isOn(val(d.id, 'state')));
      if (!on.length) return 'They are all off already.';
      if (!control()) return `That would switch off ${list(on.map(nameOf))}. Your turn is over, so it stays as it is.`;
      for (const d of on) await Home.sendControl(d.id, 'state', false);
      on.forEach(d => highlight(d.id));
      return `Switched off: ${list(on.map(nameOf))}.`;
    }],
    ['Will it rain today?', async () => {
      const w = await Home.api('/api/weather').catch(() => null), hr = (w && w.hourly) || {}, now = Date.now(), today = new Date().toDateString();
      const p = (hr.time || []).map((t, i) => [new Date(t), (hr.precipitation_probability || [])[i]])
        .filter(([t, v]) => v != null && t.toDateString() === today && t.getTime() > now - 3600e3).map(([, v]) => v);
      if (!p.length) return 'The forecast is not here yet.';
      const most = Math.max(...p);
      return most >= 50 ? `Yes, likely: up to ${most} % chance of rain later today.` : most >= 20 ? `Maybe: up to ${most} % chance of rain today.` : `No, ${most} % at most today.`;
    }],
    ['Why did the hallway light turn on?', async () => {
      const f = [...feed].reverse().find(x => x.who === 'rule' && x.device === 'Hallway light');
      return f ? `At ${new Date(f.ts * 1000).toTimeString().slice(0, 5)} a rule did it: ${f.text}.` : 'No rule has switched it on in this turn yet. Ring the doorbell or send someone into the hallway.';
    }],
    ['Lock the front door', async () => {
      const locked = ![false, 'UNLOCKED', 'unlocked'].includes(val('front_lock', 'locked'));
      if (locked) return 'The front door is locked already.';
      if (!control()) return 'It is unlocked now. Your turn is over, so it stays as it is.';
      await Home.sendControl('front_lock', 'locked', true);
      highlight('front_lock');
      return 'Done: the front door is locked.';
    }],
  ];
  const NOTE = 'The language model is not connected in this demo: pick one of the example questions to see how answers look.';
  async function askOpen(text) {
    const box = '<div style="padding:16px 18px;display:flex;flex-direction:column;gap:12px;max-width:520px">' +
      '<div class="demo-row" style="justify-content:space-between"><h2 style="margin:0">Ask the house</h2><button class="dlg-btn" data-x="close" aria-label="Close">&times;</button></div>' +
      `<p class="demo-dim" style="margin:0">${E(NOTE)}</p><div class="demo-log" data-x="log"></div>` +
      `<div class="askex">${ASK.map((q, i) => `<button class="demo-btn" data-q="${i}">${E(q[0])}</button>`).join('')}</div></div>`;
    Home.openModal(box, '__demo_ask__');
    const md = document.getElementById('md'), log = md.querySelector('[data-x=log]');
    const say = (mine, t) => { const d = document.createElement('div'); d.className = 'demo-bub' + (mine ? ' mine' : ''); d.textContent = t; log.append(d); log.scrollTop = log.scrollHeight; };
    const ask = async i => { say(true, ASK[i][0]); try { say(false, await ASK[i][1]()); } catch (e) { say(false, why(e)); } };
    md.querySelector('[data-x=close]').onclick = () => Home.closeModal();
    md.querySelectorAll('[data-q]').forEach(b => { b.onclick = () => ask(+b.dataset.q); });
    if (!text) return;
    const i = ASK.findIndex(q => q[0].toLowerCase().replace(/[?.!]/g, '') === text.toLowerCase().replace(/[?.!]/g, '').trim());
    if (i >= 0) return ask(i);
    say(true, text); say(false, NOTE);            // free text: the note again, never a model
  }
  window.__demoAsk = {questions: ASK.map(q => q[0]), answer: i => ASK[i][1]()};   // the stack's check reads the answers

  // ---- bottom tabs ----
  const svg = p => `<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">${p}</svg>`;    // drawn: a typed sign may be missing from the font
  const BOTTOM = [
    ['map', 'Map', svg('<path d="M3 3h18v18H3V3zm2 2v6h6V5H5zm8 0v4h6V5h-6zm0 6v8h6v-8h-6zM5 13v6h6v-6H5z" fill="currentColor" fill-rule="evenodd"/>'), 'p:map'],
    ['dev', 'Devices', Home.icon('switch', 20), 'switch'],
  ];
  const bar = Object.assign(document.createElement('nav'), {className: 'demo-bottom'});
  bar.innerHTML = BOTTOM.map(t => `<button data-t="${t[3]}"><span>${t[2]}</span>${t[1]}</button>`).join('');
  bar.querySelectorAll('button').forEach(b => { b.onclick = () => { Home.openTab(b.dataset.t); markBar(); }; });
  document.body.appendChild(bar);
  // ---- the simulation panel beside the live map: a left column when wide, a bottom sheet on a phone ----
  const side = Object.assign(document.createElement('aside'), {className: 'demo-side'});
  side.setAttribute('aria-label', 'Simulation');
  side.innerHTML = '<div class="sgrip"></div><div class="shead"><b>Simulation</b><span class="demo-dim"></span>' +
    '<button class="sfold" data-x="fold" aria-label="Fold the panel">&lsaquo;</button></div><div class="sbody"></div>';
  document.body.appendChild(side);
  simBox = side.querySelector('.sbody');
  const wide = () => innerWidth >= 900 || (innerWidth > innerHeight && innerWidth >= 640);
  const SNAP = {peek: 0, half: 1, full: 2}, snapPx = i => [64, Math.round(innerHeight * 0.45), Math.round(innerHeight * 0.85)][i];
  let snap = +(sessionStorage.getItem('demo-sheet') || SNAP.half);
  function sheet(i) { snap = i; sessionStorage.setItem('demo-sheet', String(i)); syncSide(); }
  function syncSide() {
    const b = document.body, nav = document.querySelector('.navblock'), bb = getComputedStyle(bar).display === 'none' ? 0 : bar.offsetHeight;
    b.classList.toggle('demo-map', (Home.activeTab ? Home.activeTab() : '') === 'p:map');
    b.classList.toggle('demo-wide', wide());
    b.classList.toggle('demo-fold', sessionStorage.getItem('demo-fold') === '1');
    b.style.setProperty('--demo-top', Math.max(0, nav ? nav.getBoundingClientRect().bottom : 0) + 'px');
    b.style.setProperty('--demo-bb', bb + 'px');
    if (!side.classList.contains('drag')) b.style.setProperty('--demo-sh', snapPx(snap) + 'px');
    side.querySelector('.sfold').innerHTML = b.classList.contains('demo-fold') ? '&rsaquo;' : '&lsaquo;';
  }
  side.querySelector('.sfold').onclick = () => { sessionStorage.setItem('demo-fold', sessionStorage.getItem('demo-fold') === '1' ? '' : '1'); syncSide(); };
  {                                                // the sheet's grip and head: drag to a height, tap to open or close
    let y0 = 0, h0 = 0, moved = false;
    const down = ev => {
      if (wide() || ev.target.closest('button')) return;
      y0 = ev.clientY; h0 = side.offsetHeight; moved = false;
      side.classList.add('drag'); ev.currentTarget.setPointerCapture(ev.pointerId);
    };
    const move = ev => {
      if (!side.classList.contains('drag')) return;
      if (Math.abs(ev.clientY - y0) > 6) moved = true;
      document.body.style.setProperty('--demo-sh', Math.max(snapPx(0), Math.min(snapPx(2), h0 + y0 - ev.clientY)) + 'px');
    };
    const up = () => {
      if (!side.classList.contains('drag')) return;
      side.classList.remove('drag');
      if (!moved) return sheet(snap === SNAP.peek ? SNAP.half : SNAP.peek);
      const h = side.offsetHeight;
      sheet([0, 1, 2].reduce((a, i) => Math.abs(snapPx(i) - h) < Math.abs(snapPx(a) - h) ? i : a, 0));
    };
    for (const el of [side.querySelector('.sgrip'), side.querySelector('.shead')]) {
      el.addEventListener('pointerdown', down); el.addEventListener('pointermove', move);
      el.addEventListener('pointerup', up); el.addEventListener('pointercancel', up);
    }
  }
  addEventListener('resize', syncSide);
  addEventListener('scroll', syncSide, {passive: true});
  function markBar() {
    syncSide();
    const cur = Home.activeTab ? Home.activeTab() : '';
    bar.querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.t === cur || (b.dataset.t === 'switch' && cur && !cur.startsWith('p:'))));
  }

  // ---- the first 20 s: a look around the flat, nothing is switched ----
  const SCENE = [
    [null, 'Welcome to a demo flat: six rooms, 42 simulated devices, the same software as a real home.'],
    ['Living room ceiling', 'Every icon is a device or a lamp on the plan. Tap one to open it.'],
    ['Hallway motion', 'Rules run by themselves: motion in the hallway at dusk switches its light on.'],
    ['living_radar', 'Three residents move through the day; radars and motion sensors see them.'],
    [null, 'One guest at a time: the flat is yours now. Try the things in the simulation panel.'],
  ];
  function scene() {
    if (sessionStorage.getItem('demo-seen')) return;
    sessionStorage.setItem('demo-seen', '1');
    const cap = Object.assign(document.createElement('div'), {className: 'demo-cap'});
    document.body.appendChild(cap);
    let i = 0;
    const step = () => {
      if (i >= SCENE.length || !cap.isConnected) { cap.remove(); return; }
      const [dev, text] = SCENE[i++];
      cap.innerHTML = `<div class="demo-row" style="justify-content:space-between"><span>${E(text)}</span><button class="demo-btn" data-x="skip">Skip</button></div><div class="bar" style="width:0"></div>`;
      cap.querySelector('[data-x="skip"]').onclick = () => cap.remove();
      requestAnimationFrame(() => { const b = cap.querySelector('.bar'); if (b) b.style.width = '100%'; });
      highlight(dev);
      setTimeout(step, 4000);
    };
    setTimeout(step, 1200);
  }

  // ---- the intro: from an empty plan to the live flat, drawn by the map's own renderer on a copy (MapScene: no taps,
  // nothing stored). A ghost pointer goes to the tool each step uses; Skip ends it; reduced motion gets stills + Next.
  const INTRO_SEEN = 'demo-intro-seen';
  const IS = [
    ['Draw the walls and doors', 'Walls: tap, tap. Openings: draw one along a wall.', 'walltool'],
    ['Name the rooms', 'New room: an outline becomes a room with its own tab.', 'newroom'],
    ['Place the devices', 'Left to place: pick a device, then tap its spot.', 'left'],
    ['Draw the lamps', 'A long press on the plan: a new lamp or an LED strip.', null],
    ['Connect them', 'A switch\'s "What it turns on": pick its lamp. A line is a wire from a switch or socket; a dashed one, IR from a blaster.', 'wires'],
    ['Teach it a rule', 'Motion in the hallway switches the hallway light on.', null],
    ['Put it on the wall', 'The panel builder lays out a tablet for the wall.', null],
    ['Your house is ready. Now play with it.', 'The flat below is live and yours until your turn ends.', null],
  ];
  const icss = document.createElement('style');
  icss.textContent = `
    .demo-intro { position: fixed; left: 0; right: 0; bottom: 0; z-index: calc(var(--z-dialog, 9000) + 500); background: #0b0e13; display: flex; flex-direction: column; transition: opacity .6s; }
    .demo-intro .ihead { padding: 10px 14px 6px; }
    .demo-intro .icap b { font-size: 17px; display: block; } .demo-intro .icap span { color: #9aa4b2; font-size: 13px; }
    .demo-intro .idots { display: flex; gap: 6px; margin-top: 8px; }
    .demo-intro .idots i { width: 8px; height: 8px; border-radius: 50%; background: #2a333d; } .demo-intro .idots i.on { background: #3d8bfd; }
    .demo-intro .imap { flex: 1; position: relative; min-height: 0; }
    .demo-intro .iside { position: absolute; left: 12px; bottom: 56px; z-index: 2; max-width: min(340px, calc(100vw - 24px)); }
    .demo-intro .icard { background: #1a2129; border: 1px solid #3d8bfd; border-radius: 12px; padding: 12px 14px; font-size: 14px; }
    .demo-intro .ipanel { width: min(340px, calc(100vw - 24px)); aspect-ratio: 1024 / 600; border: 0; border-radius: 10px; background: #000; }
    .demo-ghost { position: fixed; left: 50%; top: 50%; width: 20px; height: 20px; margin: -10px 0 0 -10px; border-radius: 50%; z-index: calc(var(--z-dialog, 9000) + 600);
      background: rgba(255,255,255,.9); box-shadow: 0 0 0 6px rgba(61,139,253,.35); pointer-events: none; transition: left .6s ease, top .6s ease; }
    .demo-ghost.tap { animation: demo-tap .45s; }
    @keyframes demo-tap { 0% { transform: scale(1); } 50% { transform: scale(.6); box-shadow: 0 0 0 14px rgba(61,139,253,.15); } 100% { transform: scale(1); } }
    .demo-intro .ipop { animation: demo-pop .5s; } @keyframes demo-pop { 0% { transform: scale(.2); } 70% { transform: scale(1.25); } 100% { transform: scale(1); } }
    .demo-intro .iglow { filter: drop-shadow(0 0 10px #ffd24d) drop-shadow(0 0 4px #ffd24d); }
    .demo-intro [data-m=left], .demo-intro [data-m=underlay], .demo-intro [data-m=walltool], .demo-intro [data-m=optool] { display: inline-block !important; }
    .demo-intro .icap { display: inline-flex; align-items: center; gap: 16px; padding: 6px 10px; border-radius: 10px; max-width: 100%; }
    .demo-intro .ibtns { display: flex; gap: 6px; flex: none; } .demo-intro .ibtns .main { background: #3d8bfd; color: #fff; }
    @media (max-width: 700px) { .demo-intro .icap { display: flex; flex-direction: column; align-items: flex-start; gap: 8px; } }
    .imark, .demo-intro .icap.imark { outline: 3px solid #FFD54A; outline-offset: 3px; border-radius: 10px; animation: demo-blink .7s ease-in-out 4; }
    .imark.imark-dev { outline-style: dashed; outline-offset: 7px; border-radius: 50%; }    /* a device: not the solid ring of a lit one */
    @media (max-width: 700px) { .demo-intro .iside { position: static; margin: 8px 0 0; max-width: none; } }      /* a phone: in the head, over the plan's top edge */
    @keyframes demo-blink { 50% { outline-color: transparent; } }
    @media (prefers-reduced-motion: reduce) { .demo-intro, .demo-ghost { transition: none; } .demo-intro .ipop, .demo-ghost.tap, .imark, .demo-intro .icap.imark { animation: none; } }`;
  document.head.appendChild(icss);

  // the frames: from the house's map (a copy) back to an empty plan, then forward one change at a time
  function introFrames(src, cands) {
    const F = [], cp = o => JSON.parse(JSON.stringify(o)), cat = id => (cands.find(c => c.id === id) || {}).category || 'other';
    const d = {rooms: src.rooms.map(r => ({...cp(r), name: ' ', walls: (r.walls || []).map(() => false)})), items: [], links: [], openings: [], walls: []};
    const push = (step, ms, change, focus) => F.push({step, ms, change, focus});
    src.rooms.forEach((r, ri) => (r.walls || []).forEach((w, wi) => { if (w) push(0, 110, x => { x.rooms[ri].walls[wi] = true; }); }));
    (src.openings || []).forEach(o => push(0, 140, x => { x.openings.push(cp(o)); }));
    src.rooms.forEach((r, ri) => push(1, 650, x => { x.rooms[ri].name = r.name; }, 'underlay'));
    const order = ['switch', 'dimmer', 'socket', 'motion', 'climate', 'door', 'button', 'lock', 'ac', 'tv', 'blaster', 'speaker', 'panel'];
    const devs = src.items.filter(i => i.kind === 'device').sort((a, b) => (order.indexOf(cat(a.dev)) + 99) % 99 - (order.indexOf(cat(b.dev)) + 99) % 99);
    devs.forEach(i => push(2, 170, x => { x.items.push(cp(i)); }, [i.id]));
    src.items.filter(i => i.kind === 'load').forEach(i => {
      if (i.path && i.path.length > 2) {
        push(3, 160, x => { x.items.push({...cp(i), path: cp(i.path.slice(0, 2))}); }, [i.id]);
        for (let k = 3; k <= i.path.length; k++) push(3, 120, x => { x.items.find(y => y.id === i.id).path = cp(i.path.slice(0, k)); });
      } else push(3, 220, x => { x.items.push(cp(i)); }, [i.id]);
    });
    (src.links || []).forEach(l => push(4, 330, x => { x.links.push(cp(l)); }, [l.load]));
    push(4, 1800, () => {}, 'radio');
    push(5, 5200, () => {}, 'rule');
    push(6, 5600, () => {}, 'panel');
    push(7, 3200, () => {}, 'end');
    return {start: d, frames: F};
  }

  async function intro(opt = {}) {
    if (!window.MapScene || document.querySelector('.demo-intro')) return;
    const still = opt.still || matchMedia('(prefers-reduced-motion: reduce)').matches;
    const speed = window.__introSpeed || 1;                 // a test plays it faster
    let src, cands, auto = [], wiring = [];
    try {
      [src, cands] = await Promise.all([Home.api('/api/map'), Home.api('/api/map/candidates')]);
      auto = await Home.api('/api/map/auto').catch(() => []);
      wiring = await Home.api('/api/wiring').then(w => (w && w.entries) || []).catch(() => []);
    } catch (e) { return; }
    localStorage.setItem(INTRO_SEEN, '1');
    const hdr = document.querySelector('header');
    const ov = Object.assign(document.createElement('div'), {className: 'demo-intro'});
    ov.style.top = Math.max(0, hdr ? hdr.getBoundingClientRect().bottom : 0) + 'px';
    ov.innerHTML = `<div class="ihead"><div class="icap"><div class="itext" aria-live="polite"></div><div class="ibtns">${still ? '<button class="demo-btn" data-i="back">Back</button><button class="demo-btn main" data-i="next">Next</button>' : ''}<button class="demo-btn" data-i="skip">Skip</button></div></div><div class="idots">${IS.map(() => '<i></i>').join('')}</div></div>
      <div class="imap"></div><div class="iside"></div>
`;
    document.body.appendChild(ov);
    const ghost = Object.assign(document.createElement('div'), {className: 'demo-ghost'});
    if (!still) document.body.appendChild(ghost);
    const {start, frames} = introFrames(src, cands);
    const work = JSON.parse(JSON.stringify(start));
    const ctl = await MapScene.render(ov.querySelector('.imap'), {data: {...JSON.parse(JSON.stringify(src)), ...work,
      underlay: src.underlay ? {...src.underlay, show: false} : src.underlay}, cands, rooms: []});
    if (!ctl) { ov.remove(); ghost.remove(); return; }
    ctl.layers(true, false);
    let step = -1, over = false;
    const side = ov.querySelector('.iside');
    if (innerWidth < 700) ov.querySelector('.ihead').append(side);       // a phone: the cards sit over the plan, never on it
    const show = i => {
      if (i === step) return;
      step = i;
      const cap = ov.querySelector('.icap');
      document.querySelectorAll('.imark').forEach(e => e.classList.remove('imark', 'imark-dev'));     // the last step's frames go
      cap.querySelector('.itext').innerHTML = `<b>${E(IS[i][0])}</b><span>${E(IS[i][1])}</span>`;
      const nx = cap.querySelector('[data-i="next"]');
      if (nx) nx.textContent = i === IS.length - 1 ? 'Start' : 'Next';
      const sk = cap.querySelector('[data-i="skip"]');
      if (sk && !nx) { sk.textContent = i === IS.length - 1 ? 'Start' : 'Skip'; sk.classList.toggle('main', i === IS.length - 1); }   // the film's end: Start
      cap.classList.remove('imark'); void cap.offsetWidth; cap.classList.add('imark');          // where to read: the step's caption
      ov.querySelectorAll('.idots i').forEach((dot, k) => dot.classList.toggle('on', k <= i));
      side.innerHTML = '';
      const tool = IS[i][2] && ctl.bar(IS[i][2]), at = !IS[i][2] ? null : tool && tool.offsetParent ? tool : ctl.bar('more');   // a step without a tool frames none
      if (at && at.offsetParent) { if (still) mark(at); else point(at, true); }
    };
    let marked = null;
    const mark = el => {                            // where to look: the step's target, framed (blinking, steady under reduced motion)
      if (!el.getBoundingClientRect().width) return;  // a strip's path has no box to frame
      if (marked && marked !== el) marked.classList.remove('imark', 'imark-dev');
      marked = el;
      el.classList.remove('imark'); void el.offsetWidth; el.classList.add('imark');
      el.classList.toggle('imark-dev', !!el.closest('.imap') && el.matches('[data-id]'));
    };
    const point = (el, tap) => {
      mark(el);
      const b = el.getBoundingClientRect();
      ghost.style.left = (b.left + b.width / 2) + 'px'; ghost.style.top = (b.top + b.height / 2) + 'px';
      if (tap) setTimeout(() => { ghost.classList.remove('tap'); void ghost.offsetWidth; ghost.classList.add('tap'); }, 600 / speed);
    };
    const park = el => {                             // a card or the tablet: framed, the pointer at its corner, not on its words
      mark(el);
      const b = el.getBoundingClientRect();
      ghost.style.left = (b.right - 4) + 'px'; ghost.style.top = (b.top + 4) + 'px';
    };
    const special = f => {
      if (f.focus === 'underlay') ctl.underlay(true);
      if (f.focus === 'radio') { ctl.lines(auto, wiring); ctl.layers(true, true); }
      if (f.focus === 'rule') {
        side.innerHTML = '<div class="icard"><b>Rule</b><br>When <b>Hallway motion</b> sees someone<br>then <b>Hallway light</b> on</div>';
        const m = (src.items.find(x => x.dev === 'Hallway motion') || {}).id, ln = (src.links || []).find(l => l.dev === 'Hallway light');
        const both = [m, ln && ln.load].filter(Boolean);
        both.forEach((id, k) => setTimeout(() => { const e = ctl.el(id); if (e) e.classList.add(k ? 'iglow' : 'ipop'); }, (600 + k * 1600) / speed));
        if (innerWidth < 700) ctl.fit();                        // a phone: the card took room in the head, the plan is shorter
        if (both.length) ctl.zoomTo(both, 2.5);                  // the rule's two devices, both in view
        park(side);
        setTimeout(() => both.forEach(id => { const e = ctl.el(id); if (e) e.classList.add('imark', 'imark-dev'); }), 300 / speed);
      }
      if (f.focus === 'panel') {
        side.innerHTML = '<iframe class="ipanel" title="The playground tablet" src="/panel-view.html?panel=playground&camslow=1"></iframe>';
        ctl.fit(); park(side);
      }
      if (f.focus === 'end') {
        ctl.fit();
        if (pill && pill.offsetParent) park(pill);      // the turn's own clock (the pill's box: its buttons are redrawn every second)
      }
    };
    const close = () => {
      over = true;
      document.removeEventListener('keydown', keys);
      document.querySelectorAll('.imark').forEach(e => e.classList.remove('imark', 'imark-dev'));
      ghost.remove();
      ov.style.opacity = '0';
      setTimeout(() => ov.remove(), 600);
      try { Home.openTab('p:map'); } catch (e) { /* no map */ }
      if (opt.done) opt.done();
    };
    ov.querySelector('[data-i="skip"]').onclick = close;
    const keys = ev => {                            // Right or Enter: next, Left: back, Esc: skip
      const b = ev.key === 'Escape' ? 'skip' : ev.key === 'ArrowRight' || ev.key === 'Enter' ? 'next' : ev.key === 'ArrowLeft' ? 'back' : '';
      const el = b && ov.querySelector(`[data-i="${b}"]`);
      if (el) { ev.preventDefault(); el.click(); }
    };
    document.addEventListener('keydown', keys);
    if (still) {                                  // one still per step: the plan as it stands at the step's end
      const ends = IS.map((_, i) => frames.reduce((k, f, n) => f.step === i ? n : k, -1));
      const at = i => {
        const x = JSON.parse(JSON.stringify(start));
        frames.slice(0, ends[i] + 1).forEach(f => f.change(x));
        ctl.set(x); ctl.fit(); ctl.underlay(false); ctl.layers(true, false); show(i);               // the plan's layers so far, and this step's own scene
        frames.slice(0, ends[i] + 1).filter(f => f.focus === 'underlay' || f.focus === 'radio' || (f.step === i && typeof f.focus === 'string')).forEach(special);
      };
      let i = 0; at(0);
      ov.querySelector('[data-i="next"]').onclick = () => { if (i >= IS.length - 1) return close(); at(++i); };
      ov.querySelector('[data-i="back"]').onclick = () => { if (i > 0) at(--i); };
      return;
    }
    let due = performance.now();                    // a clock, not a sum of waits: a slow screen draws fewer frames, not a longer film
    for (let k = 0; k < frames.length; k++) {
      const f = frames[k], next = frames[k + 1];
      if (over) return;
      show(f.step);
      f.change(work);
      due += f.ms / speed;
      if (performance.now() < due || !next || next.step !== f.step || typeof f.focus === 'string') {     // behind: the next frame draws both
        ctl.set({rooms: work.rooms, items: work.items, links: work.links, openings: work.openings});
        if (Array.isArray(f.focus)) {
          const e = ctl.el(f.focus[0]);
          if (e) { e.classList.add('ipop'); point(e, f.step === 2 || f.step === 3); }
        } else if (f.focus) special(f);
      }
      const left = due - performance.now();
      if (left > 0) await new Promise(r => setTimeout(r, left));
    }
    if (!over) close();
  }
  window.__demoIntro = intro;

  // the first turn gets the intro (once per browser); without the map's scene, the old look around
  function firstLook() {
    if (looked) return;
    looked = true;
    if (window.MapScene && !localStorage.getItem(INTRO_SEEN)) { sessionStorage.setItem('demo-seen', '1'); intro({done: helpTip}); }
    else { scene(); setTimeout(helpTip, 21000); }                  // after the 20 s look around
  }
  // the core's first-visit tip on the "?" would pop over the intro: held back here, said when the intro is over
  const tipLater = !localStorage.getItem('help.tip');
  if (tipLater) localStorage.setItem('help.tip', '1');
  function helpTip() {
    if (!tipLater) return;
    const b = document.getElementById('helpbtn');
    if (b) { b.classList.remove('hq-wiggle'); void b.offsetWidth; b.classList.add('hq-wiggle'); }
    toast('<b>The "?" top left:</b> tap it for all the hints, or drag it onto anything to see what that is.', 7000);
  }

  // a closed page says goodbye (a beacon carries no header: the token goes in the body); a hidden one just pauses
  addEventListener('pagehide', () => {
    const tok = localStorage.getItem('hs_token');
    if (tok && navigator.sendBeacon) navigator.sendBeacon('/api/demo/bye', new Blob([JSON.stringify({token: tok})], {type: 'application/json'}));
  });
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') beat(); });

  HomePlugins.register({
    header: [{slot: 'conn', render(b) { pill = b; beat(); }}],
    ask: [{open: askOpen, examples: () => ASK.map(q => q[0])}],      // the header's Ask the house
    onReload: [async () => { markHeader(); applyGrey(); }],
    settings: showSettings,           // the pages of the plug-ins this demo keeps off: what each item is
    onState: [() => drawTasks()],
  });
  // register() tags them with the demo plug-in, whose menu: false would leave them out: they stand for the plug-ins shown
  showSettings.forEach(x => { x._plugin = {}; });
  // the map is the first thing a guest sees
  if (!new URLSearchParams(location.search).get('tab') && !sessionStorage.getItem('demo-tab')) {
    sessionStorage.setItem('demo-tab', '1');
    setTimeout(() => { try { Home.openTab('p:map'); } catch (e) { /* no map */ } markBar(); ready = true; if (control()) firstLook(); }, 600);
  } else setTimeout(() => { markBar(); ready = true; if (control()) firstLook(); }, 600);
  document.addEventListener('click', () => setTimeout(markBar, 50));
  setInterval(syncSide, 1000);                    // a tab opened by the page itself (a link, the back button)
  drawSim(); drawCover();                         // the cover is up before the first render, until an answer says "control"
  let beats = 0;
  setInterval(() => { if (!control() || ++beats % 3 === 0) beat(); }, 3000);     // in line: the turn is seen within 3 s
  setInterval(poll, 2500);
  setInterval(() => {
    if (!st) return;
    if (control()) { st.left_s = Math.max(0, st.left_s - 1); st.idle_s = Math.max(0, st.idle_s - 1); }
    else if (st.position) st.eta_s = Math.max(0, st.eta_s - 1);
    drawPill(); drawCover();
  }, 1000);
})();
