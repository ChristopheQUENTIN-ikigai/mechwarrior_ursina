
from ursina import *

class LoadoutMenu(Entity):

    def __init__(self):

        super().__init__(parent=camera.ui)

        self.bg=Entity(parent=self,model='quad',scale=(.6,.6),color=color.rgba(0,0,0,180))

        Text("MECH LOADOUT",parent=self,y=.25)

        Button(text="Laser",parent=self,y=.1)
        Button(text="PPC",parent=self,y=0)
        Button(text="Missile",parent=self,y=-.1)
