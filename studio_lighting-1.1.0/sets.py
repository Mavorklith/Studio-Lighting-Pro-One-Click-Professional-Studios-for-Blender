# SPDX-License-Identifier: GPL-3.0-or-later
"""Original procedural scenery; no downloaded geometry or textures required."""
import math, random
import bpy, bmesh
from mathutils import Vector, Matrix

FAMILIES=[('ARCH','Sculpted arches'),('BOTANICAL','Botanical atelier'),('TERRACE','Stepped terraces'),
 ('HALO','Floating halos'),('FLUTED','Fluted gallery'),('DUNES','Sculpted dunes'),
 ('MONOLITH','Stone monoliths'),('RIBBON','Flowing ribbons'),('ORBIT','Orbital forms'),('PORTAL','Layered portals')]
SET_ITEMS=[('AUTO','Recipe set','A distinct composition for each studio'),('NONE','Seamless only','Remove set decoration')]+[(a,b,b) for a,b in FAMILIES]

def clear(c):
    for o in list(c.objects):
        d=o.data; mats=list(d.materials) if d and hasattr(d,'materials') else []
        bpy.data.objects.remove(o,do_unlink=True)
        if d and d.users==0:
            if isinstance(d,bpy.types.Mesh):bpy.data.meshes.remove(d)
        for m in mats:
            if m and m.users==0 and m.get('sl_set_material'):bpy.data.materials.remove(m)

def build(scene,lo,hi,palette):
    s=scene.sl_settings
    if not s.set_objects:
        s.set_objects=bpy.data.collections.new('SL • Set design');scene.collection.children.link(s.set_objects)
    clear(s.set_objects)
    if s.set_style=='NONE' or s.background=='NONE':return
    idx=int(s.studio); family=FAMILIES[idx%10][0] if s.set_style=='AUTO' else s.set_style
    rng=random.Random(941+idx*83+s.set_seed)
    radius=max((hi-lo).length*.5,.001); unit=radius*s.set_scale
    # Camera-relative coordinates: decorations are behind the entire subject's
    # horizontal bounding circle, even for long furniture and rear cameras.
    center=(lo+hi)*.5;center.z=lo.z
    cam=scene.camera
    back=Vector((center.x-cam.location.x,center.y-cam.location.y,0))
    if back.length<.00001:back=Vector((0,1,0))
    back.normalize(); right=Vector((back.y,-back.x,0))
    rotation=Matrix.Rotation(math.radians(s.set_rotation),3,'Z')
    back=rotation@back;right=rotation@right
    origin=center+back*(radius*s.set_distance)
    basis=Matrix(((right.x,back.x,0),(right.y,back.y,0),(0,0,1)))
    def point(p):return origin+basis@(Vector(p)*unit)
    def mat(name,color,metal=0,rough=.6):
        m=bpy.data.materials.new('SL • '+name);m['sl_set_material']=True;m.use_nodes=True
        p=m.node_tree.nodes.get('Principled BSDF');p.inputs['Base Color'].default_value=(*color,1)
        p.inputs['Roughness'].default_value=rough;p.inputs['Metallic'].default_value=metal
        m.diffuse_color=(*color,1);return m
    bg=palette[2]
    stone=mat('Set plaster',tuple(min(.85,v*.7+.12) for v in bg),rough=.72)
    accent=mat('Set satin',tuple(min(.8,v*.4+.09) for v in palette[0]),metal=.45,rough=.3)
    green=mat('Botanical leaves',(.035,.13+idx*.0015,.055),rough=.4) if family=='BOTANICAL' else None
    def mesh(name,verts,faces,m=stone,smooth=False,bevel=0):
        d=bpy.data.meshes.new(name);d.from_pydata([point(p) for p in verts],[],faces);d.update()
        o=bpy.data.objects.new('SL • '+name,d);s.set_objects.objects.link(o);d.materials.append(m)
        for p in d.polygons:p.use_smooth=smooth
        if bevel:
            mod=o.modifiers.new('Soft edges','BEVEL');mod.width=bevel*unit;mod.segments=3
            o.modifiers.new('Weighted normals','WEIGHTED_NORMAL')
        return o
    def box(name,c,sz,m=stone,angle=0):
        rot=Matrix.Rotation(angle,3,'Y')
        vs=[Vector(c)+rot@Vector((x*sz[0]/2,y*sz[1]/2,z*sz[2]/2)) for x,y,z in
            [(-1,-1,-1),(-1,-1,1),(-1,1,-1),(-1,1,1),(1,-1,-1),(1,-1,1),(1,1,-1),(1,1,1)]]
        return mesh(name,vs,[(0,4,6,2),(1,3,7,5),(0,1,5,4),(2,6,7,3),(0,2,3,1),(4,5,7,6)],m,bevel=.035)
    def tube(name,path,thick,m=stone):
        vs=[];n=10
        for j,p in enumerate(path):
            tangent=Vector(path[min(j+1,len(path)-1)])-Vector(path[max(0,j-1)])
            tangent.normalize();ref=Vector((0,1,0))
            if abs(tangent.dot(ref))>.95:ref=Vector((1,0,0))
            a=tangent.cross(ref).normalized();b=tangent.cross(a).normalized()
            vs.extend(Vector(p)+thick*(math.cos(k*2*math.pi/n)*a+math.sin(k*2*math.pi/n)*b) for k in range(n))
        fs=[(j*n+k,j*n+(k+1)%n,(j+1)*n+(k+1)%n,(j+1)*n+k) for j in range(len(path)-1) for k in range(n)]
        fs.extend([tuple(reversed(range(n))),tuple((len(path)-1)*n+k for k in range(n))])
        return mesh(name,vs,fs,m,True)
    def sphere(name,c,r,m=accent):
        bm=bmesh.new();bmesh.ops.create_uvsphere(bm,u_segments=32,v_segments=16,radius=r)
        for v in bm.verts:v.co=point(Vector(c)+v.co)
        d=bpy.data.meshes.new(name);bm.to_mesh(d);bm.free()
        o=bpy.data.objects.new('SL • '+name,d);s.set_objects.objects.link(o);d.materials.append(m)
        for p in d.polygons:p.use_smooth=True
    variant=idx//10
    if family=='ARCH':
        for j in range(2+variant%2):
            x=(j-.6)*1.1;h=1.1+j*.25+variant*.09;r=.7+j*.12
            path=[(x-r,j*.3,0),(x-r,j*.3,h)]+[(x+r*math.cos(t),j*.3,h+r*math.sin(t)) for t in [math.pi-k*math.pi/40 for k in range(1,41)]]+[(x+r,j*.3,0)]
            tube('Sculpted arch',path,.1+variant*.015,stone if j%2==0 else accent)
    elif family=='BOTANICAL':
        for branch in range(3+variant%2):
            x=(-1 if branch%2 else 1)*(1.05+branch*.16);sign=-1 if x<0 else 1
            path=[(x+sign*.35*t*t,.2*branch+.2*t,2.7*t) for t in [k/20 for k in range(21)]]
            tube('Stem',path,.018,green)
            for j in range(4,19,2):
                root=Vector(path[j]);side=(-1)**j if j%4 else -1
                length=rng.uniform(.45,.8);vs=[]
                for k in range(13):
                    t=k/12;w=math.sin(math.pi*t)*length*.26
                    for edge in (-1,0,1):
                        vs.append(root+Vector((side*length*t,.15*math.sin(math.pi*t)+edge*w,.25*t+(.06 if edge==0 else 0)*math.sin(math.pi*t))))
                fs=[(k*3+e,(k+1)*3+e,(k+1)*3+e+1,k*3+e+1) for k in range(12) for e in range(2)]
                leaf=mesh('Curved leaf',vs,fs,green,True)
                mod=leaf.modifiers.new('Leaf thickness','SOLIDIFY');mod.thickness=unit*.003
        box('Botanical ledge',(-1.1,.3,.15),(.8,.8,.3))
    elif family=='TERRACE':
        for j in range(4+variant%3):
            height=.3+j*(.26+variant*.035)
            box('Terrace',((j-2)*(.7+variant*.045),j*(.23+variant*.02),height/2),(.9+variant*.03,.95,height),stone if j%2 else accent)
    elif family=='HALO':
        for j in range(2+variant%2):
            r=.85+j*.35+variant*.065;path=[((j-.5)*(.65+variant*.07)+r*math.cos(t),j*.3,1.25+variant*.08+r*math.sin(t)) for t in [k*math.tau/80 for k in range(81)]]
            tube('Satin halo',path,.045+j*.025,accent)
    elif family=='FLUTED':
        for j in range(11+variant*2):
            h=1.4+.6*math.sin(j*.35+variant*.4)
            tube('Fluted column',[((j-6)*.22,.25,0),((j-6)*.22,.25,h)],.085,stone if j%4 else accent)
    elif family=='DUNES':
        for j in range(3):
            vs=[]
            for x in range(61):
                xx=-3+x*.1;h=.4+j*.32+.25*math.sin(xx*1.8+j+variant)
                vs.extend([(xx,j*.5,0),(xx,j*.5,h)])
            mesh('Dune ridge',vs,[(k*2,k*2+2,k*2+3,k*2+1) for k in range(60)],stone,True)
    elif family=='MONOLITH':
        for j in range(3+variant%2):
            h=rng.uniform(.8,2.3);box('Monolith',((j-1)*.9,j*.23,h/2),(.5,.6,h),stone if j%2 else accent,rng.uniform(-.12,.12))
    elif family=='RIBBON':
        for j in range(2+variant%2):
            vs=[]
            for k in range(81):
                t=k/80;x=-2.5+5*t;z=.65+j*.48+.45*math.sin(t*math.tau+variant*.5)
                vs.extend([(x,j*.3,z-.12),(x,j*.3+.07,z+.12)])
            o=mesh('Wave ribbon',vs,[(2*k,2*k+2,2*k+3,2*k+1) for k in range(80)],accent,True)
            mod=o.modifiers.new('Ribbon thickness','SOLIDIFY');mod.thickness=unit*.045
    elif family=='ORBIT':
        for j in range(5+variant):
            r=rng.uniform(.17,.44);sphere('Orbit sphere',(rng.uniform(-2,2),rng.uniform(0,.6),r+rng.uniform(0,1.6)),r)
    elif family=='PORTAL':
        for j in range(3):
            w=1.3+j*.5;h=1.6+j*.4+variant*.08;y=j*.35
            for x in (-w,w):box('Portal upright',(x,y,h/2),(.13,.18,h),stone if j%2 else accent)
            box('Portal lintel',(0,y,h),(w*2+.13,.18,.13),stone if j%2 else accent)
    # A material unused by a particular family is not left behind.
    for m in (stone,accent,green):
        if m and m.users==0:bpy.data.materials.remove(m)
    scene['studio_lighting_set']=family
