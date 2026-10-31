// 첫 화면이 그려지기 전에 data-view를 정한다. src/view/viewMode.ts의 resolveViewMode와 같은 규칙이며 시험이 둘을 대조한다.
(function () {
  var chosen = new URLSearchParams(location.search).get('view');
  if (chosen !== 'easy' && chosen !== 'standard') {
    try {
      chosen = sessionStorage.getItem('view');
    } catch {
      chosen = null;
    }
  }
  var view = chosen === 'easy' ? 'easy' : 'standard';
  document.documentElement.dataset.view = view;
  try {
    sessionStorage.setItem('view', view);
  } catch {
    /* 저장이 막힌 브라우저에서는 이 화면에서만 유지한다. */
  }
})();
