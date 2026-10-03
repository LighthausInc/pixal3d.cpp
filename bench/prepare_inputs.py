"""Own schematic geometry guided by storyboard art, not anatomically validated."""
import bpy, argparse, pathlib, math, json, sys, hashlib, subprocess
from mathutils import Vector
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from blender_pass import normalize,render_setup
p=argparse.ArgumentParser(); p.add_argument('--out',required=True); p.add_argument('--storyboards',required=True); a=p.parse_args(sys.argv[sys.argv.index('--')+1:]); root=pathlib.Path(a.out).resolve(); boards=pathlib.Path(a.storyboards).resolve()

def material(name,color,metal=0):
    m=bpy.data.materials.new(name); m.diffuse_color=(*color,1); m.use_nodes=True; bs=m.node_tree.nodes.get('Principled BSDF'); bs.inputs['Base Color'].default_value=(*color,1); bs.inputs['Metallic'].default_value=metal; bs.inputs['Roughness'].default_value=.38; return m

def cube(name,loc,scale,mat,bevel=.03):
    bpy.ops.mesh.primitive_cube_add(size=1,location=loc); o=bpy.context.object; o.name=name; o.scale=scale; bpy.ops.object.transform_apply(location=False,rotation=False,scale=True); o.data.materials.append(mat)
    if bevel:
        mod=o.modifiers.new('Rounded corners','BEVEL'); mod.width=bevel; mod.segments=3; bpy.context.view_layer.objects.active=o; bpy.ops.object.modifier_apply(modifier=mod.name)
    return o

def cyl(name,loc,r,depth,mat):
    bpy.ops.mesh.primitive_cylinder_add(vertices=48,radius=r,depth=depth,location=loc); o=bpy.context.object; o.name=name; o.data.materials.append(mat); mod=o.modifiers.new('Edge rounding','BEVEL'); mod.width=.012; mod.segments=3; bpy.ops.object.modifier_apply(modifier=mod.name); return o

def make(kind):
    white=material('Warm ivory',(.72,.74,.71)); dark=material('Charcoal',(.055,.067,.07)); silver=material('Brushed steel',(.56,.61,.64),.7); teal=material('Muted teal',(.12,.33,.36))
    if kind=='monitor':
        cube('cart base',(0,0,.12),(.72,.52,.11),white)
        for x in [-.30,.30]:
            for y in [-.21,.21]:
                wheel=cyl('caster',(x,y,.06),.065,.045,dark); wheel.rotation_euler.x=math.pi/2
        for x in [-.28,.28]: cube('cart upright',(x,.12,.56),(.055,.055,.82),silver,.012)
        for z in [.35,.63,.88]: cube('shelf',(0,0,z),(.70,.50,.055),white,.02)
        cube('monitor stand',(0,.05,1.02),(.12,.11,.25),silver)
        cube('monitor bezel',(0,0,1.26),(.60,.09,.44),white)
        cube('unlabelled screen',(0,-.052,1.27),(.52,.014,.35),dark,.015)
        cube('control deck',(0,-.12,.92),(.54,.28,.045),white)
        for x in [-.18,-.10,-.02,.06,.14]: cube('key',(x,-.17,.951),(.05,.028,.01),teal,.003)
    elif kind=='probe':
        cube('probe grip',(0,0,.085),(.040,.035,.12),white,.014)
        cube('flared head',(0,0,.025),(.075,.047,.042),white,.017)
        cube('transducer face',(0,0,.003),(.073,.046,.012),teal,.007)
        cyl('cable socket, no cable',(0,0,.15),.013,.02,dark)
    else:
        cyl('handle',(-.07,0,.08),.018,.16,silver)
        for z in [.025,.04,.055,.07,.085,.10,.115,.13]: cyl('grip ring',(-.07,0,z),.0187,.003,dark)
        cube('hinge',(-.055,0,.169),(.055,.036,.023),silver,.006)
        # Curved broad metal blade, with raised side flange; handle convention schematic.
        verts=[]; faces=[]
        for i in range(21):
            t=i/20; x=-.05+.18*t; z=.174-.040*t*t
            for y,dz in [(-.016,0),(.016,0),(.016,.005),(-.016,.005)]: verts.append((x,y,z+dz))
        for i in range(20):
            for j in range(4): faces.append((4*i+j,4*i+(j+1)%4,4*(i+1)+(j+1)%4,4*(i+1)+j))
        faces.extend([(3,2,1,0),(80,81,82,83)])
        me=bpy.data.meshes.new('blade'); me.from_pydata(verts,[],faces); me.update(); o=bpy.data.objects.new('Curved blade',me); bpy.context.collection.objects.link(o); o.data.materials.append(silver)
        cube('blade side flange',(.005,.014,.18),(.11,.005,.017),silver,.002)

panels={'monitor':['iut-panel-04-safe-path-with-ultrasound.jpg','amnio-panel-04-planning-an-infusion.jpg'],'probe':['iut-panel-04-safe-path-with-ultrasound.jpg','amnio-panel-04-planning-an-infusion.jpg'],'laryngoscope':['panel-10-reveal-vocal-cords.png','panel-11-place-breathing-tube.png']}
for kind in panels:
    out=root/kind; out.mkdir(parents=True,exist_ok=True); bpy.ops.wm.read_factory_settings(use_empty=True); bpy.context.scene.world=bpy.data.worlds.new('Neutral'); make(kind)
    bpy.ops.export_scene.gltf(filepath=str(out/'reference.glb'),export_format='GLB'); normalize(); cam=render_setup(1024); frames=[]
    # Explicit metadata avoids inferring camera geometry from invented reverse views.
    for name,angle in [('front',0),('back',math.pi),('left',-math.pi/2),('right',math.pi/2)]:
        cam.location=(3.119*math.sin(angle),-3.119*math.cos(angle),0); cam.rotation_euler=(-cam.location).to_track_quat('-Z','Y').to_euler(); bpy.context.view_layer.update(); bpy.context.scene.render.filepath=str(out/f'{name}.png'); bpy.ops.render.render(write_still=True)
        frames.append({'file_path':f'{name}.png','camera_angle_x':math.radians(20),'transform_matrix':[list(row) for row in cam.matrix_world]})
    (out/'transforms.json').write_text(json.dumps({'mesh_scale':1.,'camera_angle_x':math.radians(20),'frames':frames},indent=2)+'\n')
    sources=[]
    for name in panels[kind]:
        f=boards/name
        sources.append({'url':f'https://github.com/LighthausInc/mfm-quest/blob/c3ab9f070aea30884d51934893b3b3317c0c44ec/docs/storyboards/{name}','sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'use':('Laryngoscope blade guidance' if name.startswith('panel-10') else 'Adjacent airway context; panel-11 depicts ET tube, not laryngoscope' if name.startswith('panel-11') else 'Monitor and probe design guidance')+'; no panel pixels in generation inputs.'})
    rec={'schema_version':1,'asset':kind,'source':'Lighthaus own procedural schematic, prepare_inputs.py','licence':'Lighthaus internal evaluation; original schematic geometry; storyboard ownership as provided by David','source_script_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),'storyboards':sources,'reference_status':'Schematic trial reference; not clinical/medical accuracy evidence; approve before drawing product conclusions.','no_patient_or_clinical_images':True,'camera':{'fov_degrees':20,'distance':3.119,'height':0,'normalized_max_dimension':1},'probe_cable':'excluded','images':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in out.glob('*.png')}}
    (out/'provenance.json').write_text(json.dumps(rec,indent=2)+'\n')
