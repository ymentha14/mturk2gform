import pdb

import ipywidgets as widgets
from IPython.display import display
import subprocess
from pathlib import Path



class ControlPanel():
    """
    Ipywidgets panel allowing high-level control of the HITs creation,confirmation
    validation and deletion along with monitoring of number of HITs per worker

    """
    def __init__(self,turk,watcher=None):
        """
        Args:
            turk (mt2gf.Turker): turker instance which will be used through the control panel
            watcher (mt2gf.Watcher): watcher instance which will be used throught the control panel. If
            set to None, no monitoring buttons will be displayed
        """
        self.turk = turk
        self.watcher = watcher
        self.display_panel()

    def list_hits(self,b):
        """
        Button: List the published HITs. Completed designates the number of completed
        forms for the given HIT. Once Percent_completed reaches 100, the HIT status becomes "Assignable"
        """
        df = self.turk.list_hits()
        display(df,self.output)

    def create_hits(self,b):
        """
        Generate and publish the HITs tasks as described by turk.gform_map.
        """
        self.turk.create_forms_hits()

    def approve_correct_dry(self,b):
        """
        Call Turker.approve_correct_hits: this
        """
        self.turk.save_worker_infos()
        self.turk.approve_correct_hits(dry_run=True)

    def approve_correct(self,b):
        """
        """
        self.turk.save_worker_infos()
        self.turk.approve_correct_hits(dry_run=False)

    def approve_all(self,b):
        """
        """
        self.turk.save_worker_infos()
        self.turk.approve_all_hits()

    def list_assignments(self,b):
        """
        """
        display(self.turk.list_all_assignments())

    def stop_all_hits(self,b):
        """
        """
        self.turk.stop_all_hits()

    def delete_all_hits(self,b):
        """
        """
        self.turk.delete_all_hits()

    def start_monitor(self,b):
        """
        """
        self.watcher.start_monitor()

    def stop_monitor(self,b):
        """
        """
        self.watcher.stop_monitor()

    def tagged_workers(self,b):
        """
        """
        print("Tagged workers:")
        display(self.watcher.get_tagged_workers())

    def results_hitid_formidx(self,sender):
        """
        """
        df = self.turk.get_results(self.b_resform.value)
        display(df)

    def untag_all_workers(self,b):
        """
        """
        self.watcher.untag_all_workers()

    def display_panel(self):
        """
        Displays the most important features from the Turker through an Ipywidgets
        control panel in the jupyer notebook

        Args:
            turk (mt2gf.Turker): the Turker instance that will handle the actions
            gform_map_id (str): google drive id of the google forms mapping file
        """
        self.output = widgets.Output()

        approve_color = 'lightgreen'
        stop_color = 'orange'

        # 1. List hits button
        b_listhits = widgets.Button(description='list hits')
        b_listhits.on_click(self.list_hits)

        # 2. Create hits button
        # create the hits linked to the turker
        b_createhits = widgets.Button(description='create hits')
        b_createhits.on_click(self.create_hits)

        # 3. Approve correct dry run
        # same output than if approve_correct was ran with no consequence
        b_appcorrdry = widgets.Button(description='approve correct (dry)')
        b_appcorrdry.on_click(self.approve_correct_dry)
        b_appcorrdry.style.button_color = approve_color

        # 4. Approve correct HITs
        appcorr = widgets.Button(description='approve_correct')
        appcorr.on_click(self.approve_correct)
        appcorr.style.button_color = approve_color

        # 5. Approve all HITs
        b_appall = widgets.Button(description='approve all')
        b_appall.on_click(self.approve_all)
        b_appall.style.button_color = approve_color

        # 6. List all Assignments
        b_allass = widgets.Button(description='list assignments')
        b_allass.on_click(self.list_assignments)

        # 7. Stop all hits
        bstop = widgets.Button(description='stop all hits')
        bstop.on_click(self.stop_all_hits)
        bstop.style.button_color = stop_color

        # 8. Delete all hits
        bdelete = widgets.Button(description='delete all hits',button_style='danger')
        bdelete.on_click(self.delete_all_hits)

        # 9. Start a watcher thread
        bwatcher = widgets.Button(description='start monitor',button_style='info')
        bwatcher.on_click(self.start_monitor)

        # 10. Stop a monitor thread if one exists
        bstopwatcher = widgets.Button(description='stop monitor',button_style='primary')
        bstopwatcher.on_click(self.stop_monitor)

        # 11. List tagged workers a monitor thread if one exists
        btagwork = widgets.Button(description='list tagged workers',button_style='primary')
        btagwork.on_click(self.tagged_workers)

        # 12. Untag all workers
        buntagwork = widgets.Button(description='untag all workers',button_style='primary')
        buntagwork.on_click(self.untag_all_workers)

        # 12. Display downloaded result for given HITid/form idx
        self.b_resform = widgets.Text( placeholder='Results HITid/formidx')
        self.b_resform.on_submit(self.results_hitid_formidx)

        # display the buttons
        display(widgets.HBox((b_listhits, b_createhits)))
        display(widgets.HBox((b_allass,b_appall)))
        display(widgets.HBox((b_appcorrdry, appcorr)))
        display(widgets.HBox((bstop, bdelete)))
        if self.watcher is not None:
            display(widgets.HBox((bwatcher, bstopwatcher)))
            display(widgets.HBox((btagwork,buntagwork)))
        display(self.b_resform)