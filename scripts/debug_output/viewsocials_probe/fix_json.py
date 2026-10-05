import pathlib
p=pathlib.Path('scripts/debug_output/viewsocials_probe/01_storynavigation_initial_network.json')
t=p.read_text(encoding='utf-8')
t = t.replace('""x-xsrf-token"', '"x-xsrf-token"')
p.write_text(t, encoding='utf-8')
print('fixed')
