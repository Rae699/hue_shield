try {
  var p = response && response.statusCode >= 200 && response.statusCode < 300 ? JSON.parse(response.body) : null;
  var e = p && p.execution;
  var h = p && p.hdmi;
  if (e && typeof e.syncActive === 'boolean') {
    out.ok = true;
    out.active = e.syncActive;
    out.video = e.mode === 'video';
    var dimensions = h && typeof h.contentSpecs === 'string' ? /^\s*(\d+)\s*x\s*(\d+)\s*@/i.exec(h.contentSpecs) : null;
    var selected = @@INPUT@@;
    out.ready = !!(e.mode !== 'powersave' && e.hdmiActive === true && e.hdmiSource === selected &&
      h && h[selected] && h[selected].status === 'linked' && h.videoSyncSupported === true &&
      dimensions && Number(dimensions[1]) > 0 && Number(dimensions[2]) > 0);
  }
} catch (error) { out.ok = false; }
