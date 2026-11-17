"""Offline captive portal with Drawbridge branding; accepts names, never passwords."""

# Geometry from hardware/featherwing/assets/drawbridge-silkscreen.svg.
LOGO = '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" aria-hidden="true" viewBox="0 0 140 140"> <title>Drawbridge: isometric castle and lowered bridge</title> <g fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"> <polyline points="45,58 51,60 51,55 58,57 58,63 67,66 67,60 74,62 74,68 83,71 83,65 91,68 91,77"/> <polyline points="45,66 91,82"/> <polyline points="50,98 50,83 52,76 57,71 65,70 74,73 81,80 83,88 83,109"/> <polyline points="56,100 56,84 59,78 65,76 72,79 77,85 77,107"/> <polyline points="62,79 62,101"/> <polyline points="69,81 69,104"/> <polyline points="57,88 77,95"/> <polyline points="57,96 77,103"/> <polyline points="51,98 85,110 64,132 29,119 51,98"/> <polyline points="29,119 29,123 64,136 85,114 85,110"/> <polyline points="64,132 64,136"/> <polyline points="46,103 80,115"/> <polyline points="41,108 75,120"/> <polyline points="36,113 70,125"/> <polyline points="48,80 32,116"/> <polyline points="87,94 67,129"/> <polyline points="14,30 37,38 49,30 49,98 37,106 14,98 14,30"/> <polyline points="37,38 37,106"/> <polyline points="14,47 37,55 49,47"/> <polyline points="14,65 37,73 49,65"/> <polyline points="14,83 37,91 49,83"/> <polyline points="25,51 25,63"/> <polyline points="22,68 22,81"/> <polyline points="29,89 29,101"/> <polyline points="43,52 43,65"/> <polyline points="43,88 43,101"/> <polyline points="22,42 22,49"/> <polyline points="11,28 11,19 18,21 18,27 24,29 24,23 31,25 31,31 37,33 37,27 43,23 43,17 52,20 52,30 37,40 11,31 11,28"/> <polyline points="11,19 23,11 30,13 18,21"/> <polyline points="24,23 36,15 43,17 31,25"/> <polyline points="23,11 23,17"/> <polyline points="30,13 30,19"/> <polyline points="37,33 37,40"/> <polyline points="91,57 114,65 127,57 127,119 114,128 91,120 91,57"/> <polyline points="114,65 114,128"/> <polyline points="91,86 114,94 127,86"/> <polyline points="91,104 114,112 127,104"/> <polyline points="102,90 102,103"/> <polyline points="100,109 100,122"/> <polyline points="120,72 120,89"/> <polyline points="120,99 120,108"/> <polyline points="120,116 120,124"/> <polyline points="99,79 99,69 102,67 105,71 105,81 99,79"/> <polyline points="88,55 88,46 95,48 95,54 101,56 101,50 108,52 108,58 114,60 114,54 120,50 120,44 130,47 130,57 114,67 88,58 88,55"/> <polyline points="88,46 101,38 108,40 95,48"/> <polyline points="101,50 114,42 120,44 108,52"/> <polyline points="101,38 101,44"/> <polyline points="108,40 108,46"/> <polyline points="114,60 114,67"/> </g> </svg>'


def escape(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def render_page(message, networks, saved_names, device_id):
    options = ['<option value="">Choose a network</option>']
    names = list(saved_names)
    for network in networks:
        if network["ssid"] not in names:
            names.append(network["ssid"])
    for name in names:
        options.append('<option value="{0}">{0}</option>'.format(escape(name)))
    rows = []
    for name in saved_names:
        rows.append('<li><span>{0}</span><form action="/configure" method="post"><input type="hidden" name="wifi_action" value="forget"><input type="hidden" name="forget_ssid" value="{0}"><button class="quiet" type="submit" aria-label="Forget {0}">Forget</button></form></li>'.format(escape(name)))
    saved = "".join(rows) or '<li>No networks saved yet.</li>'
    return """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#173f35">
<title>Drawbridge Wi-Fi setup</title><style>
:root{{color-scheme:light;font:16px system-ui,sans-serif;color:#173f35;background:#f3f4eb}}
*{{box-sizing:border-box}}body{{max-width:34rem;margin:2rem auto;padding:0 1rem 7rem}}
header{{display:flex;align-items:center;gap:.8rem;margin-bottom:1.5rem}}h1{{font-size:1.7rem;margin:0}}h2{{font-size:1.15rem;margin:0 0 1rem}}
.subtitle,small{{color:#52665b}}.subtitle{{margin:.3rem 0}}section{{background:#fff;border:1px solid #dce2d5;border-radius:1.2rem;padding:1.2rem;margin:1rem 0}}
label{{display:block;margin:1rem 0 .4rem}}input,select{{width:100%;font:inherit;color:inherit;background:white;border:1px solid #9eafa4;border-radius:.5rem;min-height:2.8rem;padding:.65rem}}
button{{font:inherit;border:0;border-radius:.75rem;padding:.75rem 1rem;color:white;background:#173f35;min-height:2.75rem;cursor:pointer}}button:focus-visible,input:focus-visible,select:focus-visible{{outline:3px solid #bc6a26;outline-offset:3px}}
.refresh{{display:inline-block;padding:.75rem 1rem;border-radius:.75rem;text-decoration:none}}.quiet{{background:#edf2e6;color:#173f35}}.save{{position:fixed;z-index:5;bottom:1rem;left:50%;transform:translateX(-50%);width:calc(100% - 2rem);max-width:32rem;margin:0;box-shadow:0 .25rem 1rem #173f3533}}ul{{list-style:none;padding:0;margin:0}}li{{display:flex;align-items:center;justify-content:space-between;gap:.8rem;padding:.6rem 0;border-bottom:1px solid #edf2e6}}li span{{overflow-wrap:anywhere;min-width:0}}li form{{flex-shrink:0}}.check{{display:flex;align-items:center;gap:.6rem}}.check input{{width:1.2rem;min-height:1.2rem}}.notice{{background:#edf2e6;border-radius:.6rem;padding:.8rem}}small{{display:block;line-height:1.5}}footer{{font-size:.8rem;color:#52665b}}
</style></head><body><header>{logo}<div><h1>Drawbridge</h1><p class="subtitle">Wi-Fi setup &middot; {device}</p></div></header>
{notice}<section><h2>Saved networks ({count}/5)</h2><ul>{saved}</ul><small>Adding a network keeps your other locations. Passwords are never displayed.</small></section>
<section><h2>Add or update a network</h2><form action="/configure" method="post">
<label for="ssid">Saved or nearby network</label><select id="ssid" name="ssid" onchange="document.getElementById('manual-network').hidden=!!this.value;document.getElementById('ssid-manual').disabled=!!this.value">{options}</select>
<p><a class="quiet refresh" href="/scan">Refresh nearby networks</a></p>
<div id="manual-network"><label for="ssid-manual">Or enter a network name</label><input id="ssid-manual" name="ssid_manual" maxlength="32" autocomplete="off"></div>
<label for="password">Wi-Fi password</label><input id="password" name="password" type="password" maxlength="63" autocomplete="new-password">
<small>Leave blank to keep a saved password. For a new open network, no password is needed.</small>
<label class="check"><input type="checkbox" name="open_network" value="1">Open network (no password)</label>
<button class="save" type="submit">Save and connect</button></form></section>
<footer>Settings stay on this controller. Gate control is inactive during setup. To add another location, hold D1 while restarting this Feather.</footer></body></html>""".format(logo=LOGO, device=escape(device_id.lower()), notice='<p class="notice" role="status">'+escape(message)+'</p>' if message else "", count=len(saved_names), saved=saved, options="".join(options))


def render_confirmation(ssid, forgotten=False):
    title = "Network removed" if forgotten else "Wi-Fi saved"
    return """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Drawbridge Wi-Fi saved</title>
<style>:root{{font:16px system-ui,sans-serif;color:#173f35;background:#f3f4eb}}body{{max-width:30rem;margin:3rem auto;padding:1rem}}main{{background:white;border:1px solid #dce2d5;border-radius:1.2rem;padding:1.5rem}}h1{{font-size:1.6rem}}strong{{overflow-wrap:anywhere}}p{{line-height:1.5}}.count{{font-size:1.2rem}}</style></head><body>
<p>Drawbridge</p><main><h1>{title}</h1><p><strong>{ssid}</strong></p>
<p>Your other saved networks are unchanged.</p><p class="count" role="status" aria-live="polite" id="countdown">Setup Wi-Fi closes in 10 seconds.</p>
<p>You can disconnect now and reconnect your phone to your usual Wi-Fi. The controller will restart and try its saved networks; follow its screen for registration or status.</p></main>
<script>let seconds=10;const notice=document.getElementById('countdown');const timer=setInterval(()=>{{seconds--;notice.textContent=seconds>0?'Setup Wi-Fi closes in '+seconds+' seconds.':'Setup Wi-Fi is closing. Reconnect to your usual Wi-Fi.';if(seconds<=0)clearInterval(timer);}},1000);</script></body></html>""".format(title=title, ssid=escape(ssid))
