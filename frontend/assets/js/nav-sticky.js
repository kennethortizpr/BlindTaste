(function() {
  var nav = document.getElementById('nav');
  if (!nav) return;
  var ph  = document.createElement('div');
  ph.style.height  = '2.75rem';
  ph.style.display = 'none';
  nav.parentNode.insertBefore(ph, nav);
  var navTop = Infinity;
  function getAbsTop(el) { var t = 0; while (el) { t += el.offsetTop; el = el.offsetParent; } return t; }
  function update() {
    if (navTop === Infinity) return;
    var stuck = window.scrollY >= navTop;
    nav.classList.toggle('stuck', stuck);
    ph.style.display = stuck ? 'block' : 'none';
  }
  window.addEventListener('load', function() {
    nav.classList.remove('stuck');
    ph.style.display = 'none';
    navTop = getAbsTop(nav);
    update();
  });
  window.addEventListener('scroll', update, { passive: true });
})();
