import json, os, sys, time
import bpy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import portrait as PR, rig
a = sys.argv[sys.argv.index("--") + 1:]
spec = PR._deep(json.load(open(a[0])), {"lab_res": [384, 480]})
spec2, times = PR.build(spec, os.path.dirname(a[1]), "cost", 16)
sc = bpy.context.scene
for mode in a[2].split(","):
    if mode == "b2":
        sc.cycles.transmission_bounces = 2; sc.cycles.max_bounces = 4
    if mode == "b1":
        sc.cycles.transmission_bounces = 1; sc.cycles.max_bounces = 3; sc.cycles.glossy_bounces = 1
    if mode == "simple":
        import nodes as NN
        for m in bpy.data.materials:
            if m.node_tree and any(n.type == "BSDF_HAIR_PRINCIPLED" for n in m.node_tree.nodes) and m.name.startswith(("Beard", "Hair", "Brow")):
                nb = NN.NB(m)
                info = nb.node("ShaderNodeHairInfo")
                col = nb.mix((0.55, 0.52, 0.48), (0.8, 0.78, 0.74), info.outputs["Random"])
                p = nb.principled(Base_Color=col, Roughness=0.35, Sheen_Weight=0.5, Coat_Weight=0.3)
                nb.output(p.outputs[0])
    t = time.time()
    rig.render(a[1].replace(".png", "_%s.png" % mode))
    print("COST", mode, round(time.time() - t, 1))
