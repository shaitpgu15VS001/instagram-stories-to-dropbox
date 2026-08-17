from src import logger
import platform
import shutil
import pathlib
# ensure clean debug dir
sh = 'debug'
p = pathlib.Path(sh)
if p.exists():
    shutil.rmtree(p)
lg = logger.logger
lg.init_debug(debug_dir=sh, run_id='local-redact-test')
# write sensitive-looking lines
lg.info('Normal info before secrets')
lg.info('Authorization: Bearer VERY_SECRET_TOKEN_12345')
lg.error('Cookie: sessionid=COOKIE_SECRET; path=/; HttpOnly')
lg.info('Bearer token=BearerTokenXYZ')
lg.debug('password=supersecret')
lg.info('access_token=ak_abc123 refresh_token=rf_456')
lg.error('some fastdl signing param __sig=abcd1234 and __t=98765')
lg.info('random credentials: user=admin pass=hunter2')
lg.write_summary({
    'start_iso': '2026-01-01T00:00:00Z',
    'end_iso': '2026-01-01T00:00:01Z',
    'duration_seconds': 1,
    'python_version': platform.python_version(),
    'selected_backend': 'none',
    'users_loaded': 0,
    'users_processed': 0,
    'users_failed': 0,
    'files_downloaded': 0,
    'files_uploaded': 0,
    'files_skipped': 0,
    'state_total_uploaded': 0,
    'error_counts': lg.error_counts,
})
print('WROTE DEBUG FILES')
