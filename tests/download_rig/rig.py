"""Offline rig for cmd_download.

A local HTTP server stands in for GOG (Range requests, MD5 chunk XML files, injectable faults), scenarios
describe a manifest plus the starting state on disk, and run() executes cmd_download and snapshots everything
observable: file tree, manifest, log lines, exception, HTTP requests, Windows/POSIX preallocation calls.

Compare two versions of the script:  python rig.py OLD/gogrepo_delta.py NEW/gogrepo_delta.py [scenario ...]
test_download.py uses run() to check the current script against explicit expectations."""
import contextlib, hashlib, importlib.util, logging, os, pprint, random, re, shutil, sys, tempfile, threading, time, types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

for _m in ('html5lib',):
    try: __import__(_m)
    except ImportError: sys.modules[_m] = types.ModuleType(_m)

def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod; spec.loader.exec_module(mod); return mod

# ----------------------------------------------------------------------------- fake server
class Server:
    def __init__(self):
        self.files, self.xml, self.faults, self.images, self.hits, self.names = {}, {}, {}, {}, {}, {}
        self.file_bytes = 0                  # bytes of file bodies sent (not xml, not images): what really crossed the 'network'
        srv = self
        class H(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            def log_message(self, *a): pass
            def do_HEAD(self): self.serve(True)
            def do_GET(self): self.serve(False)
            def reply(self, code, body=b'', headers=(), head=False):
                self.send_response(code)
                for k, v in headers: self.send_header(k, v)
                self.send_header('Content-Length', str(len(body))); self.end_headers()
                if not head: self.wfile.write(body)
            def serve(self, head):
                path = self.path.split('?')[0]
                if path.startswith('/img/'):
                    body = srv.images.get(path[5:])
                    return self.reply(200, body, head=head) if body is not None else self.reply(404, head=head)
                key = path[len('/files/'):]
                fault = srv.faults.get(key)
                srv.hits[(self.command, key)] = srv.hits.get((self.command, key), 0) + 1
                if key in srv.xml: return self.reply(200, srv.xml[key], head=head)
                if key not in srv.files or fault == '404' or (head and fault == 'head404') or (not head and fault == 'get404'): return self.reply(404, head=head)
                data = srv.files[key]; total = len(data)
                rng = self.headers.get('Range')
                if head or not rng:
                    if not head: srv.file_bytes += len(data)
                    return self.reply(200, data if not head else b'', head=head, headers=[('Accept-Ranges', 'bytes')])
                a, b = re.match(r'bytes=(\d+)-(\d+)', rng).groups(); a, b = int(a), min(int(b), total - 1)
                body = data[a:b + 1]
                cr = 'bytes %d-%d/%d' % (a, b, total)
                if fault == 'range_wrong': cr = 'bytes %d-%d/%d' % (a, b, total + 1)
                if fault == 'truncate' or (fault == 'flaky_once' and srv.hits[('GET', key)] == 1):
                    self.send_response(206); self.send_header('Content-Range', cr); self.send_header('Content-Length', str(len(body))); self.end_headers()
                    self.wfile.write(body[:len(body) // 2]); self.wfile.flush(); self.close_connection = True; return
                if fault in ('slow', 'stall'):
                    self.send_response(206); self.send_header('Content-Range', cr); self.send_header('Content-Length', str(len(body))); self.end_headers()
                    half = len(body) // 2; self.wfile.write(body[:half]); self.wfile.flush(); time.sleep(1.3 if fault == 'slow' else 2.0)
                    if fault == 'slow': self.wfile.write(body[half:]); return
                    self.close_connection = True; return
                srv.file_bytes += len(body)
                self.reply(206, body, headers=[('Content-Range', cr)])
        class Quiet(ThreadingHTTPServer):
            def handle_error(self, request, client_address): pass
        self.httpd = Quiet(('127.0.0.1', 0), H); self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
    @property
    def base(self): return 'http://127.0.0.1:%d' % self.port
    def stop(self): self.httpd.shutdown(); self.httpd.server_close()

def blob(seed, size): return random.Random(seed).randbytes(size)
def md5hex(b): return hashlib.md5(b).hexdigest()

def chunk_xml(name, data, chunk=1000, total=None, chunks=None, method='md5', corrupt_hash=False):
    parts = [(i, min(i + chunk, len(data)) - 1) for i in range(0, len(data), chunk)]
    body = ''.join('<chunk id="%d" from="%d" to="%d" method="%s">%s</chunk>' % (n, a, b, method, md5hex(data[a:b + 1]) if not corrupt_hash else 'bad') for n, (a, b) in enumerate(parts))
    return ('<file name="%s" available="1" notavailablemsg="" md5="%s" total_size="%d" chunks="%d">%s</file>'
            % (name, md5hex(data), len(data) if total is None else total, len(parts) if chunks is None else chunks, body)).encode()

class World:
    """Builds server content and manifest entries for one scenario."""
    def __init__(self, srv): self.srv = srv; self.items = []
    def file(self, game, name, seed, size, xml='chunks', kind='downloads', os_type='windows', lang='English', fault=None, flags=None, manifest_size=None, xml_override=None, xml_chunk=1000, key=None):
        data = blob(seed, size); key = key or '%s__%s' % (game, name)
        self.srv.files[key] = data; self.srv.names[key] = name
        if xml_override is not None: self.srv.xml[key + '.xml'] = xml_override
        elif xml == 'chunks': self.srv.xml[key + '.xml'] = chunk_xml(name, data, chunk=xml_chunk)
        if fault: self.srv.faults[key] = fault
        e = dict(name=name, desc='desc of ' + name, version='1.%d' % (seed % 5), size=size if manifest_size is None else manifest_size,
                 href='%s/files/%s' % (self.srv.base, key), md5=md5hex(data), updated='2020-01-01T00:00:00+00:00', unreleased=False)
        if kind != 'extras': e.update(lang=lang, os_type=os_type)
        e.update(flags or {}); return e, data
    def game(self, gid, title, **kw):
        g = dict(id=gid, title=title, long_title='%s: the long title' % title, genre='RPG', store_url='/game/%s' % title, rating=45, release_timestamp=1500000000,
                 changelog='', has_updates=False, serial='', bg_url='', image_url='', downloads=[], galaxyDownloads=[], sharedDownloads=[], extras=[])
        g.update(kw); self.items.append(g); return g

DEFAULTS = dict(skipextras=False, skipids=[], dryrun=False, ids=[], os_list=['windows', 'linux', 'mac'], lang_list=['en', 'de'],
                skipgalaxy=False, skipstandalone=False, skipshared=False, skipfiles=[], covers=False, backgrounds=False,
                skippreallocation=False, clean_old_images=False, downloadLimit=None)

def put(root, rel, data):
    p = os.path.join(root, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'wb') as f: f.write(data)

# ----------------------------------------------------------------------------- scenarios
SCENARIOS = {}
def scenario(f): SCENARIOS[f.__name__[3:]] = f; return f

def standard_world(srv):
    w = World(srv)
    a = w.game(1, 'alpha', serials={'key1': 'AAAA-<span>BBBB</span>', 'key2': 'CCCC'}, changelog='changelog text', gog_messages=['hello <b>msg</b>'])
    a['downloads'] = [w.file('alpha', 'setup_alpha.exe', 1, 2500)[0], w.file('alpha', 'setup_alpha-1.bin', 2, 3100, xml=None)[0],
                      w.file('alpha', 'setup_alpha_linux.sh', 3, 1500, os_type='linux')[0], w.file('alpha', 'setup_alpha_de.exe', 4, 1800, lang='Deutsch')[0]]
    a['galaxyDownloads'] = [w.file('alpha', 'galaxy_alpha.exe', 5, 1200)[0]]
    a['sharedDownloads'] = [w.file('alpha', 'shared_alpha.exe', 6, 900, xml=None)[0]]
    a['extras'] = [w.file('alpha', 'manual.pdf', 7, 700, xml=None, kind='extras')[0], w.file('alpha', 'soundtrack.zip', 8, 1700, xml=None, kind='extras')[0]]
    b = w.game(2, 'beta', folder_name='Beta Game', serial='SER-<span>IAL</span>')
    b['downloads'] = [w.file('beta', 'setup_beta.exe', 9, 2100)[0]]
    b['extras'] = [w.file('beta', 'extra_beta.exe', 10, 1100, kind='extras')[0]]
    return w

@scenario
def sc_dryrun_fresh(srv, root):
    w = standard_world(srv); return dict(items=w.items, kwargs=dict(dryrun=True))
@scenario
def sc_fresh_download(srv, root):
    w = standard_world(srv); return dict(items=w.items, kwargs={})
@scenario
def sc_filter_os_lang(srv, root):
    w = standard_world(srv); return dict(items=w.items, kwargs=dict(os_list=['linux'], lang_list=['en']))
@scenario
def sc_filter_de_only(srv, root):
    w = standard_world(srv); return dict(items=w.items, kwargs=dict(lang_list=['de']))
@scenario
def sc_skip_flags(srv, root):
    w = standard_world(srv); return dict(items=w.items, kwargs=dict(skipextras=True, skipgalaxy=True, skipshared=True))
@scenario
def sc_skip_standalone(srv, root):
    w = standard_world(srv); return dict(items=w.items, kwargs=dict(skipstandalone=True))
@scenario
def sc_skipfiles(srv, root):
    w = standard_world(srv); return dict(items=w.items, kwargs=dict(skipfiles=['*.pdf', 'setup_alpha-*']))
@scenario
def sc_ids_by_title_and_id(srv, root):
    w = standard_world(srv); return dict(items=w.items, kwargs=dict(ids=['alpha']))
@scenario
def sc_skipids(srv, root):
    w = standard_world(srv); return dict(items=w.items, kwargs=dict(skipids=['1']))
@scenario
def sc_ids_not_found(srv, root):
    w = standard_world(srv); return dict(items=w.items, kwargs=dict(ids=['nope']))
@scenario
def sc_ids_and_skipids_empty(srv, root):
    w = standard_world(srv); return dict(items=w.items, kwargs=dict(ids=['alpha'], skipids=['alpha']))
@scenario
def sc_download_limit(srv, root):
    w = standard_world(srv); return dict(items=w.items, kwargs=dict(downloadLimit=6000))
@scenario
def sc_existing_files(srv, root):
    w = standard_world(srv)
    def setup(r):
        put(r, 'alpha/setup_alpha.exe', srv.files['alpha__setup_alpha.exe'])                          # ok -> pass
        put(r, 'alpha/setup_alpha_de.exe', b'x' * 5000)                                                 # too big -> re-fetched
        put(r, 'alpha/setup_alpha_linux.sh', b'y' * 10)                                                 # too small -> re-fetched
        put(r, 'alpha/galaxy_alpha.exe', srv.files['alpha__galaxy_alpha.exe'])
        w.items[0]['galaxyDownloads'][0]['force_change'] = True; w.items[0]['galaxyDownloads'][0]['prev_verified'] = True   # marked for change
    return dict(items=w.items, kwargs={}, setup=setup)
@scenario
def sc_force_change_flags(srv, root):
    w = standard_world(srv)
    for g in w.items:
        for k in ('downloads', 'extras'):
            for e in g[k]: e['force_change'] = True; e['prev_verified'] = True; e['old_updated'] = None
    def setup(r):
        for g in w.items:
            for k in ('downloads', 'extras'):
                for e in g[k]: put(r, '%s/%s' % (g.get('folder_name', g['title']), e['name']), srv.files[[x for x in srv.files if x.endswith('__' + e['name'])][0]])
    return dict(items=w.items, kwargs={}, setup=setup)
@scenario
def sc_all_up_to_date(srv, root):
    w = standard_world(srv)
    def setup(r):
        for g in w.items:
            for k in ('downloads', 'galaxyDownloads', 'sharedDownloads', 'extras'):
                for e in g[k]: put(r, '%s/%s' % (g.get('folder_name', g['title']), e['name']), srv.files[[x for x in srv.files if x.endswith('__' + e['name'])][0]])
    return dict(items=w.items, kwargs={}, setup=setup)
@scenario
def sc_resume_chunk_repair(srv, root):
    w = standard_world(srv)
    def setup(r):
        good = srv.files['alpha__setup_alpha.exe']; bad = bytearray(good); bad[1200:1300] = b'\0' * 100; bad[2300:] = b''     # corrupt chunk 1, short tail
        put(r, '!downloading/alpha/setup_alpha.exe', bytes(bad))
        put(r, '!downloading/Beta Game/setup_beta.exe', srv.files['beta__setup_beta.exe'][:1500] + b'\xff' * 600)         # right size, bad tail
    return dict(items=w.items, kwargs={}, setup=setup)
@scenario
def sc_resume_without_chunks(srv, root):
    w = standard_world(srv)
    def setup(r): put(r, '!downloading/alpha/setup_alpha-1.bin', b'partial' * 100)
    return dict(items=w.items, kwargs={}, setup=setup)
@scenario
def sc_resume_oversized_partial(srv, root):
    w = standard_world(srv)
    def setup(r): put(r, '!downloading/alpha/setup_alpha.exe', b'z' * 9000)
    return dict(items=w.items, kwargs={}, setup=setup)
@scenario
def sc_provisional_files(srv, root):
    w = standard_world(srv)
    def setup(r):
        put(r, '!downloading/!provisional/alpha/manual.pdf', srv.files['alpha__manual.pdf'])
        put(r, '!downloading/!provisional/Beta Game/extra_beta.exe', srv.files['beta__extra_beta.exe'])
        w.items[0]['extras'][0]['force_change'] = True; w.items[0]['extras'][0]['prev_verified'] = True
    return dict(items=w.items, kwargs={}, setup=setup)
@scenario
def sc_provisional_only(srv, root):
    w = standard_world(srv)
    def setup(r):
        for g in w.items:
            for k in ('downloads', 'galaxyDownloads', 'sharedDownloads', 'extras'):
                for e in g[k]:
                    if e['name'] != 'manual.pdf': put(r, '%s/%s' % (g.get('folder_name', g['title']), e['name']), srv.files[[x for x in srv.files if x.endswith('__' + e['name'])][0]])
        put(r, '!downloading/!provisional/alpha/manual.pdf', srv.files['alpha__manual.pdf'])
    return dict(items=w.items, kwargs={}, setup=setup)
@scenario
def sc_provisional_only_flags(srv, root):
    """Like provisional_only, and the finished file belongs to an entry that is marked 'needs update' and 'verified'."""
    d = SCENARIOS['provisional_only'](srv, root)
    entry = d['items'][0]['extras'][0]
    entry['force_change'] = True; entry['prev_verified'] = True
    return d
@scenario
def sc_provisional_and_dest(srv, root):
    w = standard_world(srv)
    def setup(r):
        put(r, '!downloading/!provisional/alpha/manual.pdf', srv.files['alpha__manual.pdf']); put(r, 'alpha/manual.pdf', b'already here')
    return dict(items=w.items, kwargs={}, setup=setup)
@scenario
def sc_cleanup_dirs(srv, root):
    w = standard_world(srv)
    def setup(r):
        put(r, '!downloading/old_game/file.bin', b'1'); put(r, '!downloading/alpha/stale.bin', b'2'); os.makedirs(os.path.join(r, '!downloading/alpha/sub/deep'))
        put(r, '!downloading/!provisional/old_game2/f.bin', b'3'); put(r, '!downloading/!provisional/alpha/stale2.bin', b'4'); os.makedirs(os.path.join(r, '!downloading/!provisional/alpha/subdir'))
    return dict(items=w.items, kwargs={}, setup=setup)
@scenario
def sc_cleanup_dirs_dryrun(srv, root):
    d = SCENARIOS['cleanup_dirs'](srv, root); d['kwargs'] = dict(dryrun=True); return d
@scenario
def sc_faults(srv, root):
    w = World(srv); g = w.game(1, 'faulty')
    g['downloads'] = [w.file('faulty', 'missing.exe', 1, 1500, fault='404')[0], w.file('faulty', 'headfail.exe', 2, 1500, fault='head404')[0],
                      w.file('faulty', 'badrange.exe', 3, 1500, fault='range_wrong')[0], w.file('faulty', 'badrange_nochunk.bin', 4, 1500, xml=None, fault='range_wrong')[0],
                      w.file('faulty', 'truncated.exe', 5, 2500, fault='truncate')[0], w.file('faulty', 'truncated_nochunk.bin', 6, 2500, xml=None, fault='truncate')[0],
                      w.file('faulty', 'flaky.exe', 7, 2500, fault='flaky_once')[0], w.file('faulty', 'flaky_nochunk.bin', 8, 2500, xml=None, fault='flaky_once')[0],
                      w.file('faulty', 'good.exe', 9, 1200)[0]]
    return dict(items=w.items, kwargs={})
@scenario
def sc_bad_xml(srv, root):
    w = World(srv); g = w.game(1, 'xmls'); d = {}
    def add(name, seed, size, **kw): e, data = w.file('xmls', name, seed, size, **kw); g['downloads'].append(e); return data
    data = blob(1, 2200)
    add('size_mismatch.exe', 1, 2200, xml_override=chunk_xml('size_mismatch.exe', data, total=9999))
    add('chunk_count.exe', 2, 2200, xml_override=chunk_xml('chunk_count.exe', blob(2, 2200), chunks=7))
    add('not_md5.exe', 3, 2200, xml_override=chunk_xml('not_md5.exe', blob(3, 2200), method='sha1'))
    add('bad_hash.exe', 4, 2200, xml_override=chunk_xml('bad_hash.exe', blob(4, 2200), corrupt_hash=True))
    add('garbage_xml.exe', 5, 2200, xml_override=b'<<<not xml')
    return dict(items=w.items, kwargs={})
@scenario
def sc_images(srv, root):
    w = standard_world(srv)
    w.items[0]['image_url'] = '//images.test/covers/alpha'; w.items[0]['bg_urls'] = {'1920': '//images.test/bg/alpha_1920', '1280': '//images.test/bg/alpha_1280'}
    del w.items[0]['bg_url']
    w.items[1]['image_url'] = '//images.test/covers/beta'; w.items[1]['bg_url'] = '//images.test/bg/beta'
    for p in ('covers/alpha.jpg', 'bg/alpha_1920.jpg', 'bg/alpha_1280.jpg', 'covers/beta.jpg', 'bg/beta.jpg'): srv.images['images.test/' + p] = blob(len(p), 300)
    return dict(items=w.items, kwargs=dict(covers=True, backgrounds=True))
@scenario
def sc_images_replace_old(srv, root):
    d = SCENARIOS['images'](srv, root)
    def setup(r):
        put(r, 'alpha/!images/bg_urls/old1/x/old.jpg', b'old'); put(r, 'alpha/!images/image_url/images.test/covers/stale.jpg', b'stale')
        put(r, 'Beta Game/!images/bg_url/images.test/bg/other.jpg', b'other')
    d['setup'] = setup; d['kwargs'] = dict(covers=True, backgrounds=True, clean_old_images=True); return d
@scenario
def sc_images_replace_old_noclean(srv, root):
    d = SCENARIOS['images_replace_old'](srv, root); d['kwargs']['clean_old_images'] = False; return d
@scenario
def sc_images_missing_on_server(srv, root):
    d = SCENARIOS['images'](srv, root); srv.images.clear(); return d
@scenario
def sc_skippreallocation(srv, root):
    d = SCENARIOS['resume_oversized_partial'](srv, root); d['kwargs'] = dict(skippreallocation=True); return d
@scenario
def sc_renamed_game_and_file(srv, root):
    w = standard_world(srv)
    w.items[1]['old_folder_name'] = 'beta_old_dir'; w.items[1]['old_title'] = 'beta_old_dir'
    w.items[0]['downloads'][0]['old_name'] = 'old_setup_alpha.exe'
    def setup(r): put(r, 'beta_old_dir/setup_beta.exe', srv.files['beta__setup_beta.exe']); put(r, 'alpha/old_setup_alpha.exe', srv.files['alpha__setup_alpha.exe'])
    return dict(items=w.items, kwargs={}, setup=setup)
@scenario
def sc_serial_variants(srv, root):
    w = World(srv)
    w.game(1, 'noserial'); w.game(2, 'emptyserials', serials={}); w.game(3, 'oldserial', serial='ONLY-<span>OLD</span>')
    return dict(items=w.items, kwargs={})


def listing(w, srv):
    out = []
    for g in w.items:
        for k in ('downloads', 'galaxyDownloads', 'sharedDownloads', 'extras'):
            for e in g[k]: out.append((g, e))
    return out
def fs_put_all(srv, w, r, skip=()):
    for g, e in listing(w, srv):
        if e['name'] not in skip: put(r, '%s/%s' % (g.get('folder_name', g['title']), e['name']), srv.files[[x for x in srv.files if x.endswith('__' + e['name'])][0]])

@scenario
def sc_skipids_only_empty(srv, root):
    w = standard_world(srv); return dict(items=w.items, kwargs=dict(skipids=['1', 'beta']))
@scenario
def sc_odd_entries(srv, root):
    w = standard_world(srv); g = w.items[0]
    e1, _ = w.file('alpha', 'noname.exe', 21, 800); e1['name'] = None
    e2, _ = w.file('alpha', 'nosize.exe', 22, 800); e2['size'] = None
    e3, _ = w.file('alpha', 'noupdated.exe', 23, 800); del e3['updated']
    g['downloads'] += [e1, e2, e3]; return dict(items=w.items, kwargs={})
@scenario
def sc_images_dirs_exist(srv, root):
    d = SCENARIOS['images'](srv, root)
    def setup(r):
        put(r, 'alpha/!images/bg_urls/1920/images.test/bg/old_name.jpg', b'o'); put(r, 'alpha/!images/bg_url/images.test/old/x.jpg', b'o2')
        put(r, 'alpha/!images/image_url/images.test/covers/other.jpg', b'o3')
    d['setup'] = setup; d['kwargs'] = dict(covers=True, backgrounds=True, clean_old_images=True); return d
@scenario
def sc_images_dirs_exist_noclean(srv, root):
    d = SCENARIOS['images_dirs_exist'](srv, root); d['kwargs']['clean_old_images'] = False; return d
@scenario
def sc_images_move_fails(srv, root):
    d = SCENARIOS['images_dirs_exist'](srv, root)
    def boom(*a, **k): raise OSError('simulated move failure')
    d['patch'] = lambda mod: [(mod, 'move_with_increment_on_clash', boom)]; return d
@scenario
def sc_images_rmtree_fails(srv, root):
    d = SCENARIOS['images_dirs_exist_noclean'](srv, root)
    def boom(*a, **k): raise OSError('simulated rmtree failure')
    d['patch'] = lambda mod: [(shutil, 'rmtree', boom)]; return d
def _interrupt(sub):
    def f(srv, root):
        d = SCENARIOS['images'](srv, root)
        def hook(url):
            if sub in url: raise KeyboardInterrupt()
        d['request_hook'] = hook; return d
    return f
SCENARIOS['images_interrupt_cover'] = _interrupt('covers/alpha'); SCENARIOS['images_interrupt_bg_urls'] = _interrupt('bg/alpha'); SCENARIOS['images_interrupt_bg_url'] = _interrupt('bg/beta')
@scenario
def sc_get404_and_stall(srv, root):
    w = World(srv); g = w.game(1, 'g404')
    g['downloads'] = [w.file('g404', 'get404.exe', 1, 1500, fault='get404')[0], w.file('g404', 'get404_nochunk.bin', 2, 1500, xml=None, fault='get404')[0],
                      w.file('g404', 'stall.exe', 3, 2500, fault='stall')[0], w.file('g404', 'stall_nochunk.bin', 4, 2500, xml=None, fault='stall')[0], w.file('g404', 'ok.exe', 5, 900)[0]]
    return dict(items=w.items, kwargs={}, timeout=0.5)
@scenario
def sc_slow_download(srv, root):
    w = World(srv); g = w.game(1, 'slowgame')
    g['downloads'] = [w.file('slowgame', 'slow.exe', 1, 4000, fault='slow')[0], w.file('slowgame', 'slow_nochunk.bin', 2, 4000, xml=None, fault='slow')[0]]
    return dict(items=w.items, kwargs={})
@scenario
def sc_worker_unhandled_exception(srv, root):
    w = standard_world(srv)
    def hook(mod):
        orig = mod.process_path
        def boom(path):
            if path.endswith('setup_beta.exe'): raise ValueError('boom')
            return orig(path)
        return [(mod, 'process_path', boom)]
    return dict(items=w.items, kwargs={}, patch=hook)
@scenario
def sc_worker_ioerror(srv, root):
    w = standard_world(srv)
    def hook(mod):
        orig = mod.request_head
        def boom(session, url, *a, **k):
            if 'beta' in url: raise IOError('simulated disk problem')
            return orig(session, url, *a, **k)
        return [(mod, 'request_head', boom)]
    return dict(items=w.items, kwargs={}, patch=hook)

def mixed_prealloc_world(srv):
    w = standard_world(srv); return w
def mixed_prealloc_setup(srv, w):
    def setup(r):
        put(r, 'alpha/setup_alpha_linux.sh', b'y' * 10)                                                   # dest exists, too small -> moved + grown
        put(r, 'alpha/setup_alpha_de.exe', b'x' * 6000)                                                   # dest exists, too big -> moved + truncated
        put(r, '!downloading/alpha/setup_alpha.exe', srv.files['alpha__setup_alpha.exe'][:700])            # partial smaller -> grown
        put(r, '!downloading/alpha/galaxy_alpha.exe', b'g' * 4000)                                          # partial bigger -> truncated
        put(r, '!downloading/Beta Game/setup_beta.exe', srv.files['beta__setup_beta.exe'])                 # partial exact size
    return setup
def _mixed(platform_mode=None, fs=None, **extra):
    def f(srv, root):
        w = mixed_prealloc_world(srv); d = dict(items=w.items, kwargs=dict(extra.get('kwargs', {})), setup=mixed_prealloc_setup(srv, w))
        if platform_mode: d['platform'] = platform_mode
        if fs: d['fs'] = fs
        d.update({k: v for k, v in extra.items() if k != 'kwargs'}); return d
    return f
SCENARIOS['prealloc_linux_ext4'] = _mixed()
SCENARIOS['prealloc_linux_unlisted_fs'] = _mixed(fs='overlay')
SCENARIOS['prealloc_linux_skip'] = _mixed(kwargs=dict(skippreallocation=True))
SCENARIOS['prealloc_linux_fallocate_fails'] = _mixed(fallocate_fails=True)
SCENARIOS['prealloc_windows_ntfs'] = _mixed('Windows')
SCENARIOS['prealloc_windows_skip'] = _mixed('Windows', kwargs=dict(skippreallocation=True))
SCENARIOS['prealloc_windows_unlisted_fs'] = _mixed('Windows', fs='ReFS')
SCENARIOS['prealloc_windows_createfile_fails'] = _mixed('Windows', windows_fail=True)
SCENARIOS['prealloc_darwin'] = _mixed('Darwin')

@scenario
def sc_empty_manifest(srv, root):
    return dict(items=[], kwargs={})
@scenario
def sc_images_cover_move_fails(srv, root):
    w = standard_world(srv); w.items[0]['image_url'] = '//images.test/covers/alpha'; srv.images['images.test/covers/alpha.jpg'] = blob(1, 300)
    def boom(*a, **k): raise OSError('simulated move failure')
    return dict(items=w.items, kwargs=dict(covers=True, clean_old_images=True), patch=lambda mod: [(mod, 'move_with_increment_on_clash', boom)],
                setup=lambda r: put(r, 'alpha/!images/image_url/images.test/covers/other.jpg', b'x'))
@scenario
def sc_images_bgkeys_move_fails(srv, root):
    w = standard_world(srv); w.items[0]['bg_urls'] = {'1920': '//images.test/bg/alpha_1920'}; del w.items[0]['bg_url']; srv.images['images.test/bg/alpha_1920.jpg'] = blob(2, 300)
    def boom(*a, **k): raise OSError('simulated move failure')
    return dict(items=w.items, kwargs=dict(backgrounds=True, clean_old_images=True), patch=lambda mod: [(mod, 'move_with_increment_on_clash', boom)],
                setup=lambda r: put(r, 'alpha/!images/bg_urls/1920/images.test/bg/old.jpg', b'x'))
@scenario
def sc_images_bgkeys_stale_move_fails(srv, root):
    w = standard_world(srv); w.items[0]['bg_urls'] = {'1920': '//images.test/bg/alpha_1920'}; del w.items[0]['bg_url']; srv.images['images.test/bg/alpha_1920.jpg'] = blob(2, 300)
    def boom(*a, **k): raise OSError('simulated move failure')
    return dict(items=w.items, kwargs=dict(backgrounds=True, clean_old_images=True), patch=lambda mod: [(mod, 'move_with_increment_on_clash', boom)],
                setup=lambda r: put(r, 'alpha/!images/bg_urls/stale_slug/images.test/bg/old.jpg', b'x'))
@scenario
def sc_ssl_error_while_downloading(srv, root):
    import requests
    w = World(srv); g = w.game(1, 'sslgame')
    g['downloads'] = [w.file('sslgame', 'ssl.bin', 1, 1500, xml=None)[0], w.file('sslgame', 'fine.bin', 2, 900, xml=None)[0]]
    class Wrap:
        def __init__(self, r): self._r = r
        def __getattr__(self, n): return getattr(self._r, n)
        def iter_content(self, chunk_size=1): raise requests.exceptions.SSLError('simulated')
    def hook(url, resp, k): return Wrap(resp) if url.endswith('ssl.bin') and k.get('byte_range') else resp
    return dict(items=w.items, kwargs={}, response_hook=hook)
@scenario
def sc_range_request_raises(srv, root):
    import requests
    w = World(srv); g = w.game(1, 'conngame')
    g['downloads'] = [w.file('conngame', 'conn.exe', 1, 2500)[0], w.file('conngame', 'conn_nochunk.bin', 2, 2500, xml=None)[0], w.file('conngame', 'fine.exe', 3, 900)[0]]
    def hook(url):
        if url.endswith('conn.exe') or url.endswith('conn_nochunk.bin'): raise requests.exceptions.ConnectionError('simulated')
    return dict(items=w.items, kwargs={}, request_hook=hook)
@scenario
def sc_rmdir_fails(srv, root):
    d = SCENARIOS['fresh_download'](srv, root)   # leaves empty game dirs in !downloading and !provisional -> final clean-up tries os.rmdir
    def boom(*a, **k): raise OSError('simulated')
    d['patch'] = lambda mod: [(os, 'rmdir', boom)]; return d
SCENARIOS['prealloc_windows_late_failure'] = _mixed('Windows', windows_fail_late=True)
SCENARIOS['prealloc_windows_createfile_raises'] = _mixed('Windows', windows_raises=True)   # the one intended difference (old: UnboundLocalError)

@scenario
def sc_images_covers_only(srv, root):
    d = SCENARIOS['images'](srv, root); d['kwargs'] = dict(covers=True, backgrounds=False); return d
@scenario
def sc_images_backgrounds_only(srv, root):
    d = SCENARIOS['images'](srv, root); d['kwargs'] = dict(covers=False, backgrounds=True); return d
@scenario
def sc_faults_large_truncate(srv, root):
    """Bodies larger than the 4 KB read size, so a truncated response delivers some bytes before failing."""
    w = World(srv); g = w.game(1, 'bigfaults')
    g['downloads'] = [w.file('bigfaults', 'trunc_big.exe', 1, 12000, fault='truncate', xml_chunk=12000)[0],
                      w.file('bigfaults', 'trunc_big_nochunk.bin', 2, 12000, xml=None, fault='truncate')[0],
                      w.file('bigfaults', 'flaky_big.exe', 3, 12000, fault='flaky_once', xml_chunk=12000)[0],
                      w.file('bigfaults', 'flaky_big_nochunk.bin', 4, 12000, xml=None, fault='flaky_once')[0],
                      w.file('bigfaults', 'fine_big.exe', 5, 12000, xml_chunk=12000)[0]]
    return dict(items=w.items, kwargs={})

def lang_world(srv):
    """Four games: de+en installers / English only / German Windows but English-only Linux / French only."""
    w = World(srv)
    a = w.game(1, 'alpha')
    a['downloads'] = [w.file('alpha', 'setup_alpha_en.exe', 1, 1500)[0], w.file('alpha', 'setup_alpha_de.exe', 2, 1600, lang='Deutsch')[0]]
    b = w.game(2, 'beta')
    b['downloads'] = [w.file('beta', 'setup_beta_en.exe', 3, 1400)[0]]
    c = w.game(3, 'gamma')
    c['downloads'] = [w.file('gamma', 'setup_gamma_de.exe', 4, 1300, lang='Deutsch')[0], w.file('gamma', 'setup_gamma_en.exe', 5, 1200)[0],
                      w.file('gamma', 'setup_gamma_linux_en.sh', 6, 1100, os_type='linux')[0]]
    d = w.game(4, 'delta')
    d['downloads'] = [w.file('delta', 'setup_delta_fr.exe', 7, 1000, lang='fran\u00e7ais')[0]]
    return w
@scenario
def sc_lang_fallback_download(srv, root):
    return dict(items=lang_world(srv).items, kwargs=dict(lang_list=['de'], os_list=['windows', 'linux'], lang_fallback='en'))
@scenario
def sc_lang_strict_download(srv, root):
    return dict(items=lang_world(srv).items, kwargs=dict(lang_list=['de'], os_list=['windows', 'linux']))

@scenario
def sc_unicode_names(srv, root):
    """Titles, folder names and file names in Chinese, Japanese, Russian and with accents."""
    w = World(srv)
    a = w.game(1, '\u4e2d\u6587\u6e38\u620f \u0412\u0435\u0434\u044c\u043c\u0430\u043a', long_title='\u4e2d\u6587\u6e38\u620f\uff1a\u5deb\u5e083 \u2014 \u0412\u0435\u0434\u044c\u043c\u0430\u043a 3', changelog='<p>\u66f4\u65b0\u65e5\u5fd7 \u2714 Caf\u00e9</p>')   # folder = title
    a['downloads'] = [w.file('u1', 'setup_\u5deb\u59083_\u72c2\u730e.exe', 1, 1200, key='u1__setup')[0]]
    a['extras'] = [w.file('u1', '\u0432\u0435\u0434\u044c\u043c\u0430\u043a_manual_\u65e5\u672c\u8a9e.pdf', 2, 800, xml=None, kind='extras', key='u1__manual')[0]]
    b = w.game(2, '\u65e5\u672c\u8a9e\u306e\u30b2\u30fc\u30e0', folder_name='japanese_game', long_title='\u30b2\u30fc\u30e0 \ud55c\uad6d\uc5b4 \u0e44\u0e17\u0e22')   # ASCII folder, like GOG's slugs
    b['downloads'] = [w.file('u2', 'setup_japan.exe', 3, 1000, key='u2__setup')[0]]
    return dict(items=w.items, kwargs={})

# ----------------------------------------------------------------------------- runner
class Cap(logging.Handler):
    def __init__(self): super().__init__(logging.INFO); self.records = []
    def emit(self, r): self.records.append((r.levelname, r.getMessage()))
PROGRESS = re.compile(r'^\s*[\d.]+MB\s+[\d.]+MB/s|^[\d.]+GB remaining$')

def snapshot_tree(root):
    out = {}
    for d, dirs, files in os.walk(root):
        for x in dirs: out[os.path.relpath(os.path.join(d, x), root).replace(os.sep, '/') + '/'] = None
        for x in files:
            p = os.path.join(d, x)
            with open(p, 'rb') as f: out[os.path.relpath(p, root).replace(os.sep, '/')] = (os.path.getsize(p), hashlib.sha1(f.read()).hexdigest())
    return out

class FakeKernel32:
    """Stands in for ctypes.windll.kernel32 and emulates the file effects on the real file system."""
    def __init__(self, log, fail, fail_late=False, raises=False): self.log, self.fail, self.fail_late, self.raises, self.path, self.ptr = log, fail, fail_late, raises, None, 0
    def CreateFileW(self, path, access, share, sec, disp, flags, tmpl):
        self.log.append(('CreateFileW', path, hex(access), share, disp))
        if self.raises: raise OSError('simulated: CreateFileW raised')
        if self.fail: return -1
        self.path = path[4:] if path.startswith('\\\\?\\') else path
        if disp == 1: open(self.path, 'wb').close()
        return 7
    def SetFilePointerEx(self, h, pos, newpos, method): self.ptr = pos.value; self.log.append(('SetFilePointerEx', h, pos.value, method))
    def SetEndOfFile(self, h):
        if self.fail_late: self.log.append(('SetEndOfFile-fails', h)); raise OSError('simulated late failure')
        with open(self.path, 'r+b') as f: f.truncate(self.ptr)
        self.log.append(('SetEndOfFile', h))
    def CloseHandle(self, h): self.log.append(('CloseHandle', h))

def run(mod, name):
    """Run one scenario against `mod`; return a normalised snapshot of everything observable."""
    import ctypes, ctypes.wintypes, platform
    from unittest import mock
    from types import SimpleNamespace
    work = tempfile.mkdtemp(prefix='rig_'); srv = Server(); cwd = os.getcwd(); os.chdir(work)
    savedir = os.path.join(work, 'save'); os.makedirs(savedir)
    spec = SCENARIOS[name](srv, savedir)
    if spec.get('setup'): spec['setup'](savedir)
    with open('gog-token.dat', 'w') as f: pprint.pprint({'access_token': 'x', 'refresh_token': 'y', 'expiry': time.time() + 1e9, 'user': 'u'}, stream=f)
    mod.save_manifest(spec['items'])
    orig_request, port, calls = mod.request, srv.port, []
    def patched_request(session, url, *a, **k):
        if spec.get('request_hook'): spec['request_hook'](url)
        if url.startswith('https://'): url = 'http://127.0.0.1:%d/img/%s' % (port, url[len('https://'):])
        resp = orig_request(session, url, *a, **k)
        return spec['response_hook'](url, resp, k) if spec.get('response_hook') else resp
    plat = spec.get('platform', 'Linux'); fs = spec.get('fs', 'NTFS' if plat == 'Windows' else 'ext4')   # never the host's own platform
    def fake_fs(path, isWindows=False): calls.append(('get_fs_type', path, isWindows)); return fs
    real_fallocate = getattr(os, 'posix_fallocate', None)
    def emulated_fallocate(fd, offset, length):   # hosts without os.posix_fallocate (Windows): make sure the file is at least this long
        if os.fstat(fd).st_size < offset + length: os.ftruncate(fd, offset + length)
    def fallocate(fd, offset, length):
        calls.append(('posix_fallocate', offset, length))
        if spec.get('fallocate_fails'): raise OSError('simulated')
        return (real_fallocate or emulated_fallocate)(fd, offset, length)
    patches = [(mod, 'request', patched_request), (mod, 'get_fs_type', fake_fs), (mod, 'HTTP_RETRY_DELAY', 0), (mod, 'HTTP_RETRY_COUNT', 1),
               (mod, 'HTTP_TIMEOUT', spec.get('timeout', mod.HTTP_TIMEOUT)), (os, 'posix_fallocate', fallocate)]
    patches.append((platform, 'system', lambda: plat))
    if plat == 'Windows': patches.append((ctypes, 'windll', SimpleNamespace(kernel32=FakeKernel32(calls, spec.get('windows_fail'), spec.get('windows_fail_late'), spec.get('windows_raises')))))
    patches += spec.get('patch', lambda m: [])(mod)
    logger = logging.getLogger('gogrepoc'); old_handlers, old_level = logger.handlers[:], logger.level
    cap = Cap(); logger.handlers = [cap]; logger.setLevel(logging.INFO)
    kwargs = dict(DEFAULTS); kwargs.update(spec['kwargs']); kwargs['savedir'] = savedir
    exc = None
    if hasattr(mod, 'run_report'): mod.run_report.reset('download')    # versions without a run report are still comparable
    try:
        with contextlib.ExitStack() as st:
            for obj, attr, val in patches: st.enter_context(mock.patch.object(obj, attr, val, create=True))
            try: mod.cmd_download(**kwargs)
            except SystemExit as e: exc = ('SystemExit', str(e.code))
            except BaseException as e: exc = (type(e).__name__, str(e))
    finally:
        logger.handlers = old_handlers; logger.setLevel(old_level)
    norm = lambda s: re.sub(r'127\.0\.0\.1:\d+', 'HOST', s.replace(work, '<W>'))
    logs = sorted((lvl, norm(m)) for lvl, m in cap.records if not PROGRESS.match(m))
    loaded = mod.load_manifest('gog-manifest.dat')
    manifest = norm(repr(loaded))
    plain = lambda x: {k: plain(v) for k, v in x.items()} if isinstance(x, dict) else [plain(v) for v in x] if isinstance(x, list) else x
    manifest_obj = plain(loaded)
    served = {srv.names.get(k, k.split('__', 1)[1]): hashlib.sha1(v).hexdigest() for k, v in srv.files.items()}
    tree = snapshot_tree(savedir)
    report = {'counts': {k: list(v) for k, v in mod.run_report.counts.items()}, 'failures': list(mod.run_report.failures)} if hasattr(mod, 'run_report') else None
    info_texts = {}
    for rel, value in tree.items():
        if value and os.path.basename(rel) in ('!info.txt', '!serial.txt'):
            with open(os.path.join(savedir, *rel.split('/')), encoding='utf-8') as f: info_texts[rel] = f.read()
    calls = sorted(norm(repr(c)) for c in calls)
    hits = {k: v for k, v in srv.hits.items()}
    os.chdir(cwd); srv.stop(); shutil.rmtree(work, ignore_errors=True)
    return dict(logs=logs, manifest=manifest, tree=tree, exc=exc, hits=hits, calls=calls, manifest_obj=manifest_obj, served=served, info_texts=info_texts, report=report, file_bytes=srv.file_bytes)

def compare(a, b):
    diffs = []
    for key in ('exc', 'tree', 'manifest', 'logs', 'hits', 'calls'):
        if a[key] != b[key]: diffs.append(key)
    return diffs

if __name__ == '__main__':
    old_path = sys.argv[1]; new_path = sys.argv[2]; only = sys.argv[3:] or list(SCENARIOS)   # paths to two versions of gogrepo_delta.py
    old, new = load_module(os.path.abspath(old_path), 'old_g'), load_module(os.path.abspath(new_path), 'new_g')
    bad = 0
    for name in only:
        t = time.time(); a = run(old, name); b = run(new, name); d = compare(a, b)
        status = 'same' if not d else 'DIFFERENT: ' + ','.join(d)
        print('%-30s %-5.1fs files=%-3d logs=%-3d exc=%-24s %s' % (name, time.time() - t, len([k for k, v in a['tree'].items() if v]), len(a['logs']), a['exc'] and a['exc'][0], status))
        if d:
            bad += 1
            if 'logs' in d:
                sa, sb = list(a['logs']), list(b['logs'])
                for x in a['logs']:
                    if x in sb: sb.remove(x); sa.remove(x)
                print('   only in old:', sa[:4]); print('   only in new:', sb[:4])
            if 'tree' in d: print('   tree diff:', {k: (a['tree'].get(k), b['tree'].get(k)) for k in set(a['tree']) | set(b['tree']) if a['tree'].get(k) != b['tree'].get(k)})
    print('\nscenarios different: %d of %d' % (bad, len(only)))
