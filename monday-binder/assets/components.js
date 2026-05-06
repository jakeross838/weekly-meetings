/* Schedule Intelligence — shared rendering helpers
   All functions are pure and return HTML strings (no DOM mutation).
   Density chips, status icons, flag badges, sub/phase links. */

(function (root) {
  'use strict';

  /* ------------------------ Density chip ------------------------ */
  // absolute label: continuous | steady | scattered | dragging
  // vs_phase label: above_phase | at_phase | below_phase
  // primary_pct: numeric (0..1) — formatted as % integer
  function densityClassFromAbsolute(label) {
    switch (label) {
      case 'continuous': return 'cont';
      case 'steady':     return 'stdy';
      case 'scattered':  return 'scat';
      case 'dragging':   return 'drag';
      default:           return 'empty';
    }
  }

  function vsClassFromLabel(label) {
    switch (label) {
      case 'above_phase': return 'above';
      case 'at_phase':    return 'at';
      case 'below_phase': return 'below';
      default:            return 'empty';
    }
  }

  function vsArrow(label) {
    switch (label) {
      case 'above_phase': return '▲'; // ▲
      case 'at_phase':    return '●'; // ●
      case 'below_phase': return '▼'; // ▼
      default:            return '—'; // —
    }
  }

  function vsText(label) {
    switch (label) {
      case 'above_phase': return 'above peer';
      case 'at_phase':    return 'at peer';
      case 'below_phase': return 'below peer';
      default:            return '';
    }
  }

  function capitalize(s) { return (s || '').charAt(0).toUpperCase() + (s || '').slice(1); }

  function fmtPct(num) {
    if (num === null || num === undefined || isNaN(num)) return '';
    return Math.round(num * 100) + '%';
  }

  // primaryPct: numeric primary_density (0..1) or null
  // absolute: 'continuous' | 'steady' | 'scattered' | 'dragging' | null
  // vsPhase:  'above_phase' | 'at_phase' | 'below_phase' | null
  function renderDensityChip(absolute, vsPhase, primaryPct) {
    if (absolute === null || absolute === undefined) {
      return '<span class="density-chip empty"><span class="dot"></span><span class="label">—</span></span>';
    }
    const cls = densityClassFromAbsolute(absolute);
    const pct = fmtPct(primaryPct);
    const absChip =
      '<span class="density-chip ' + cls + '">' +
        '<span class="dot"></span>' +
        (pct ? ('<span class="pct">' + pct + '</span>') : '') +
        '<span class="label">' + capitalize(absolute) + '</span>' +
      '</span>';
    if (!vsPhase) return absChip;
    const vCls = vsClassFromLabel(vsPhase);
    const vsChip =
      '<span class="vs-chip ' + vCls + '">' +
        '<span class="arrow">' + vsArrow(vsPhase) + '</span>' +
        '<span class="text">' + vsText(vsPhase) + '</span>' +
      '</span>';
    return '<span class="density-pair">' + absChip + '<span class="sep">·</span>' + vsChip + '</span>';
  }

  function renderDensityChipAbsoluteOnly(absolute, primaryPct) {
    return renderDensityChip(absolute, null, primaryPct);
  }

  function renderVsChip(vsPhase) {
    if (!vsPhase) return '<span class="vs-chip empty">—</span>';
    const cls = vsClassFromLabel(vsPhase);
    return '<span class="vs-chip ' + cls + '">' +
      '<span class="arrow">' + vsArrow(vsPhase) + '</span>' +
      '<span class="text">' + vsText(vsPhase) + '</span>' +
    '</span>';
  }

  /* ------------------------ Status icon ------------------------ */
  function renderStatusIcon(status) {
    let cls = 'empty', glyph = '—', text = '';
    switch (status) {
      case 'complete':
        cls = 'complete'; glyph = '✓'; text = 'complete'; break;
      case 'ongoing':
        cls = 'ongoing'; glyph = '⏵'; text = 'ongoing'; break;
      case 'scheduled':
        cls = 'scheduled'; glyph = '▢'; text = 'scheduled'; break;
      default:
        return '<span class="status-icon empty"><span class="glyph">—</span></span>';
    }
    return '<span class="status-icon ' + cls + '">' +
      '<span class="glyph">' + glyph + '</span>' +
      '<span class="text">' + text + '</span>' +
    '</span>';
  }

  /* ------------------------ Flag badge ------------------------ */
  function renderFlagBadge(flagScore, flagReasons) {
    if (!flagScore) return '';
    const reasons = (flagReasons && flagReasons.length)
      ? flagReasons.map(r => r.replace(/_/g, ' ')).join(' + ')
      : '';
    const reasonEl = reasons ? ('<span class="reasons">' + reasons + '</span>') : '';
    return '<span class="flag-badge" title="' + reasons + '">' +
      '<span class="glyph">⚠</span>' +
      '<span>FLAGGED</span>' +
      '<span>score ' + flagScore + '</span>' +
      reasonEl +
    '</span>';
  }

  function renderFlagPill(flagScore) {
    if (!flagScore) return '';
    return '<span class="flag-badge" style="padding:0 5px"><span class="glyph">⚠</span><span>' + flagScore + '</span></span>';
  }

  /* ------------------------ Links ------------------------ */
  function slugify(s) {
    return (s || '')
      .toString()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '');
  }

  function renderSubLink(subName) {
    if (!subName) return '';
    const slug = slugify(subName);
    return '<a class="sub-link" href="phase-library.html#sub-' + slug + '" data-sub="' + escapeHtml(subName) + '">' +
      escapeHtml(subName) +
    '</a>';
  }

  function renderPhaseLink(phaseCode, phaseName) {
    if (!phaseCode) return '';
    const slug = slugify(phaseCode);
    const label = phaseName
      ? (phaseCode + ' ' + phaseName)
      : phaseCode;
    return '<a class="phase-link" href="phase-library.html#phase-' + slug + '" data-phase="' + escapeHtml(phaseCode) + '">' +
      escapeHtml(label) +
    '</a>';
  }

  function renderJobLink(jobShort) {
    if (!jobShort) return '';
    const slug = slugify(jobShort);
    return '<a class="job-link" href="jobs.html#job-' + slug + '" data-job="' + escapeHtml(jobShort) + '">' +
      escapeHtml(jobShort) +
    '</a>';
  }

  /* ------------------------ Helpers ------------------------ */
  function escapeHtml(s) {
    if (s === null || s === undefined) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function fmtDays(d) {
    if (d === null || d === undefined || d === '' || isNaN(d)) return '—';
    return Math.round(d) + ' d';
  }

  function fmtRange(p25, p75) {
    if (p25 === null || p25 === undefined || p75 === null || p75 === undefined) return '';
    return 'P25–P75: ' + Math.round(p25) + '–' + Math.round(p75);
  }

  function pluralize(n, single, plural) {
    return n === 1 ? single : (plural || (single + 's'));
  }

  /* ------------------------ Burst role summary ------------------------ */
  function renderBurstRoles(bursts) {
    if (!bursts || !bursts.length) return '';
    const counts = { primary: 0, return: 0, punch: 0, pre_work: 0 };
    bursts.forEach(b => { if (b.burst_role && counts[b.burst_role] !== undefined) counts[b.burst_role]++; });
    const parts = [];
    if (counts.primary)  parts.push(counts.primary + ' primary');
    if (counts.return)   parts.push(counts.return + ' return');
    if (counts.punch)    parts.push(counts.punch + ' punch');
    if (counts.pre_work) parts.push(counts.pre_work + ' pre-work');
    return parts.join(' · ');
  }

  /* ------------------------ Public ------------------------ */
  root.SI = {
    renderDensityChip: renderDensityChip,
    renderDensityChipAbsoluteOnly: renderDensityChipAbsoluteOnly,
    renderVsChip: renderVsChip,
    renderStatusIcon: renderStatusIcon,
    renderFlagBadge: renderFlagBadge,
    renderFlagPill: renderFlagPill,
    renderSubLink: renderSubLink,
    renderPhaseLink: renderPhaseLink,
    renderJobLink: renderJobLink,
    renderBurstRoles: renderBurstRoles,
    escapeHtml: escapeHtml,
    fmtDays: fmtDays,
    fmtPct: fmtPct,
    fmtRange: fmtRange,
    pluralize: pluralize,
    slugify: slugify,
    capitalize: capitalize,
    densityClass: densityClassFromAbsolute,
    vsClass: vsClassFromLabel
  };
})(typeof window !== 'undefined' ? window : this);
