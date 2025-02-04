# Copyright (C) 2020 Joris Zimmermann

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program. If not, see https://www.gnu.org/licenses/.

"""TRNpy: Parallelized TRNSYS simulation with Python.

TRNpy: Parallelized TRNSYS simulation with Python
=================================================
Simulate TRNSYS deck files in serial or parallel and use parametric tables to
perform simulations for different sets of parameters. TRNpy helps to automate
these and similar operations by providing functions to manipulate deck files
and run TRNSYS simulations from a programmatic level.

Module Misc
-----------
This is a collection of miscellaneous functions that are often useful
when working with TRNpy. These are often wrappers around functions provided
by other modules such as Pandas, Bokeh, Scikit-Optimize and DataExplorer.
"""

import os
import logging
import multiprocessing
import pandas as pd
import yaml
import time
from collections.abc import Sequence
from bokeh.command.bootstrap import main
from bokeh.plotting import figure
from bokeh.models import HoverTool, ColumnDataSource, RangeTool
from bokeh.layouts import column
from bokeh.palettes import Spectral11 as palette_default

# Define the logging function
logger = logging.getLogger(__name__)


def df_to_excel(df, path, sheet_names=[], styles=[], merge_cells=False,
                check_permission=True, **kwargs):
    """Write one or more DataFrames to Excel files.

    Can save a single DataFrame to a single Excel file or multiple DataFrames
    to a combined Excel file with one sheet per DataFrame.
    Is a wrapper around pandas' function ``DataFrame.to_excel()``, which
    creates the required directory.
    In case of a ``PermissionError`` (happens when the Excel file is currently
    opended), the file is instead saved with a time stamp.

    The list ``styles`` allows some basic formatting of specific cells,
    defined by one dict per sheet in the workbook. In the example below,
    a format 'format_EUR' is defined in terms of cell format and width
    and assigned to certain columns:

    .. code:: python

        excel_fmt_eur = '_-* #,##0 €_-;-* #,##0 €_-;_-* "-" €_-;_-@_-'
        styles=[{'columns': {'B:Z': 'format_EUR'},
                 'formats': {'format_EUR': {'num_format': excel_fmt_eur}},
                 'widths': {'format_EUR': 12}}]

    Additional keyword arguments are passed down to ``to_excel()``.

    The function calls itself recursively to achieve those features.

    Args:
        df (DataFrame or list): Pandas DataFrame object(s) to save

        path (str): The full file path to save the DataFrame to

        sheet_names (list, optional): List of sheet names to use when saving
        multiple DataFrames to the same Excel file

        styles (list, optional): List of dicts that contain settings for
        formatting specific cells, one dict per sheet. Dicts must have the
        keys "columns", "formats" and "widths", see example above.

        merge_cells (boolean, optional): Write MultiIndex and Hierarchical
        Rows as merged cells. Default False.

        check_permission (boolean, optional): If the file already exists,
        instead try to save with an appended time stamp.

        freeze_panes (tuple or boolean, optional): Per default, the sheet
        cells are frozen to always keep the index visible (by determining the
        correct coordinate ``tuple``). Use ``False`` to disable this.

    Returns:
        None
    """
    if check_permission:
        try:
            # Try to complete the function without this permission check
            df_to_excel(df, path, sheet_names=sheet_names, styles=styles,
                        merge_cells=merge_cells, check_permission=False,
                        **kwargs)
            return  # Do not run the rest of the function
        except PermissionError as e:
            # If a PermissionError occurs, run the whole function again, but
            # with another file path (with appended time stamp)
            logger.critical(e)
            ts = time.localtime()
            ts = time.strftime('%Y-%m-%d_%H-%M-%S', ts)
            path_time = (os.path.splitext(path)[0] + '_' +
                         ts + os.path.splitext(path)[1])
            logger.critical('Writing instead to:  '+path_time)
            df_to_excel(df, path_time, sheet_names=sheet_names, styles=styles,
                        merge_cells=merge_cells, **kwargs)
            return  # Do not run the rest of the function

    # Here the 'actual' function content starts:
    if not os.path.exists(os.path.dirname(path)):
        logging.debug('Create directory ' + os.path.dirname(path))
        os.makedirs(os.path.dirname(path))

    if isinstance(df, Sequence) and not isinstance(df, str):
        # Save a list of DataFrame objects into a single Excel file
        writer = pd.ExcelWriter(path)
        for i, df_ in enumerate(df):
            try:  # Use given sheet name, or just an enumeration
                sheet = str(sheet_names[i])
            except IndexError:
                sheet = str(i)

            # Add current sheet to the ExcelWriter by calling this
            # function recursively
            df_to_excel(df=df_, path=writer, sheet_name=sheet,
                        merge_cells=merge_cells, **kwargs)

            # Try adding format styles to the workbook sheets
            if len(styles) > 0:
                try:
                    workbook = writer.book
                    worksheet = writer.sheets[sheet]
                    formats = styles[i]['formats']
                    wb_formats = dict()
                    for fmt_name, format_ in formats.items():
                        # Example: format_ = {'num_format': '0%'}
                        wb_formats[fmt_name] = workbook.add_format(format_)

                    columns = styles[i]['columns']
                    widths = styles[i]['widths']
                    for col, fmt_name in columns.items():
                        # Set the format and width of the column
                        worksheet.set_column(col, widths[fmt_name],
                                             wb_formats[fmt_name])
                except Exception as ex:
                    logger.exception(ex)
                    pass

        writer.save()  # Save the actual Excel file

    else:
        # Per default, the sheet cells are frozen to keep the index visible
        if 'freeze_panes' not in kwargs or kwargs['freeze_panes'] is True:
            # Find the right cell to freeze in the Excel sheet
            if merge_cells:
                freeze_rows = len(df.columns.names) + 1
            else:
                freeze_rows = 1

            kwargs['freeze_panes'] = (freeze_rows, len(df.index.names))
        elif kwargs['freeze_panes'] is False:
            del(kwargs['freeze_panes'])

        # Save one DataFrame to one Excel file
        df.to_excel(path, merge_cells=merge_cells, **kwargs)


def df_set_filtered_to_NaN(df, filters, mask, value=float('NaN')):
    """Set DataFrame values to NaN, based on filters and mask.

    Set all rows defined by the ``mask`` of the columns that are
    included in the ``filters`` to ``NaN`` (or to the optional ``value``).

    This is useful for filtering out time steps where a component is not
    active from mean values calculated later.
    """
    for column_ in df.columns:
        for filter_ in filters:
            if filter_ in column_ or filter_ == column_:
                df[column_][mask] = value
                break  # Break inner for-loop if one filter was matched
    return df


def bokeh_stacked_vbar(df_in, stack_labels=[], stack_labels_neg=[],
                       tips_cols=[], palette=palette_default, y_label=None,
                       sum_circle_size=0, **kwargs):
    """Create stacked vertical bar plot in Bokeh from TRNSYS results.

    By default, all columns in the DataFrame will be plotted. Pass ``None``
    to stack_labels and/or stack_labels_neg to prevent that, or pass a list
    with specific column names. If columns in stack_labels_neg are positive,
    they will be made negative.

    If ``sum_circle_size`` is set ``> 0`` a circle with the sum is plotted.

    The x-axis will have two groups: hash and TIME.

    Use ``**kwargs`` to pass additional keyword arguments to ``figure()`` like
    ``plot_width``, etc.
    """
    # Apply logic for default behaviour
    if stack_labels is not None:
        if len(stack_labels) == 0:
            # If no columns are set, use all existing columns
            stack_labels = [c for c in df_in.columns if df_in[c].sum() >= 0]
    else:  # If stack_labels is None, then use an empty list
        stack_labels = []

    if stack_labels_neg is not None:
        if len(stack_labels_neg) == 0:
            # If no columns are set, use all existing columns
            stack_labels_neg = [c for c in df_in.columns if df_in[c].sum() < 0]
    else:  # If stack_labels_neg is None, then use an empty list
        stack_labels_neg = []

    # Filter out non-existing columns
    stack_labels = [c for c in stack_labels if c in df_in.columns]
    stack_labels_neg = [c for c in stack_labels_neg if c in df_in.columns]

    # Filter out empty columns
    stack_labels = [c for c in stack_labels if any(df_in[c] != 0)]
    stack_labels_neg = [c for c in stack_labels_neg if any(df_in[c] != 0)]

    # Prepare Data
    df = df_in.reset_index()  # Remove index

    for col in stack_labels_neg:
        # Make sure values in the 'negative' list are actually negative
        if df[col].sum() > 0:
            df[col] = df[col] * -1
    # Calculate new column 'sum' with sum of each row
    df['sum'] = df[stack_labels].sum(axis=1) + df[stack_labels_neg].sum(axis=1)

    group_names = ['hash', 'TIME']
    for col in group_names:
        if col == 'hash':  # Add leading zero for correct string sorting
            df[col] = [str(df[col][i]).zfill(2) for i in df[col].index]
        else:
            df[col] = df[col].astype(str)  # The axis label needs strings

    df.set_index(group_names, inplace=True)  # Rebuild index
    group = df.groupby(level=group_names)
    source = ColumnDataSource(data=df)

    # Create Plot
    p = figure(x_range=group, **kwargs)
    x_sel = source.column_names[0]  # An artificial column 'hash_TIME'

    r_pos = p.vbar_stack(stack_labels, x=x_sel, width=1, source=source,
                         color=palette[0:len(stack_labels)],
                         name=stack_labels,
                         legend_label=[x+" " for x in stack_labels],
                         line_width=0,  # Prevent outline for height of 0
                         )

    if len(p.legend) > 0:
        p.legend[0].items.reverse()  # Reverse order of legend entries

    if len(stack_labels_neg) > 0:
        palette_neg = palette[-len(stack_labels_neg):]
    else:
        palette_neg = []
    r_neg = p.vbar_stack(stack_labels_neg, x=x_sel, width=1, source=source,
                         color=palette_neg, name=stack_labels_neg,
                         legend_label=[x+" " for x in stack_labels_neg],
                         line_width=0,  # Prevent outline for height of 0
                         )
    r_circ = []
    if sum_circle_size > 0:
        r = p.circle(x_sel, 'sum', source=source, legend_label='Sum',
                     name='sum', color=palette[len(stack_labels)+1],
                     size=sum_circle_size)
        r_circ.append(r)

    # Create HoverTool
    tips_list = [(col, "@{"+col+"}") for col in tips_cols]
    for r in r_pos+r_neg+r_circ:
        label = r.name
        hover = HoverTool(tooltips=[(label, "@{"+label+"}"), *tips_list],
                          renderers=[r])
        p.add_tools(hover)
    # Bokeh 0.13.0: Use $name field
    # tips_list = [(col, "@{"+col+"}") for col in param_table.columns]
    # hover = HoverTool(tooltips=[("$name ", "@$name"), *tips_list])
    # p.add_tools(hover)

    p.x_range.range_padding = 0.03  # Extra space on left and right borders
    p.outline_line_color = None
    p.xgrid.grid_line_color = None
    p.xaxis.major_label_orientation = 1.2
    if p.legend:
        p.legend.background_fill_alpha = 0.5
        p.legend.location = "top_left"
        p.legend.click_policy = "hide"
        # p.toolbar.autohide = True  # TODO Seems bugged
    if y_label is not None:
        p.yaxis.axis_label = y_label
    return p


def bokeh_sorted_load_curve(df, index_level='hash', x_col='TIME', y_label=None,
                            y_cols_line=[], y_cols_stacked=[],
                            palette=palette_default, export_file=False,
                            **kwargs):
    """Create sorted annual load curve.

    The lines can be plotted as is, or stacked.
    """
    from pandas.tseries.frequencies import to_offset

    # Filter out non-existing columns
    y_cols_line = [col for col in y_cols_line if col in df.columns]
    y_cols_stacked = [col for col in y_cols_stacked if col in df.columns]

    # Filter out empty columns (test for NaN and 0)
    y_cols_line = [col for col in y_cols_line if any(df[col].notna())]
    y_cols_stacked = [col for col in y_cols_stacked if any(df[col].notna())]
    y_cols_line = [c for c in y_cols_line if any(df[c] != 0)]
    y_cols_stacked = [c for c in y_cols_stacked if any(df[c] != 0)]

    fig_list = []  # List of Bokeh figure objects
    df_sort_line_list = []
    hash_list = []

    for hash_ in sorted(set(df.index.get_level_values(index_level))):
        df_plot = df.loc[(hash_, slice(None), slice(None)), :]  # use hash only
        df_plot = df_plot.reset_index()  # Remove index
        df_plot.set_index(x_col, inplace=True)  # Make time the only index

        # Create index for x axis of new plot
        freq = pd.to_timedelta(to_offset(pd.infer_freq(df_plot.index)))
        timedelta = df_plot.index[-1] - (df_plot.index[0] - freq)
        index = pd.timedelta_range(start=freq, end=timedelta, freq=freq,
                                   name=x_col) / pd.Timedelta(1, 'h')

        # Create a new DataFrame and fill it with the sorted values
        df_sorted_line = pd.DataFrame(index=index)
        for y_col in y_cols_line:
            sort = df_plot.sort_values(by=y_col, axis=0, ascending=False)
            df_sorted_line[y_col] = sort[y_col].values

        df_sorted_stacked = pd.DataFrame(index=index)
        for y_col in y_cols_stacked:
            sort = df_plot.sort_values(by=y_col, axis=0, ascending=False)
            df_sorted_stacked[y_col] = sort[y_col].values

        df_sorted_stacked.fillna(value=0, inplace=True)
        df_sorted_stacked = df_sorted_stacked.cumsum(axis=1, skipna=False)

        # Create the Bokeh source object used for plotting
        source_line = ColumnDataSource(data=df_sorted_line)
        source_stacked = ColumnDataSource(data=df_sorted_stacked)

        p = figure(title=str(hash_), **kwargs)
        for y_col, color in zip(y_cols_line, palette):
            p.line(x_col, y_col, legend_label=y_col+' ', line_width=2,
                   source=source_line, color=color, name=y_col)

        for y_col, color in zip(y_cols_stacked, palette[len(y_cols_line):]):
            p.line(x_col, y_col, legend_label=y_col+' ', line_width=2,
                   source=source_stacked, color=color, name=y_col)

        hover = HoverTool(tooltips='$name: @$name')
        p.add_tools(hover)
        if p.legend:
            p.legend.location = "top_right"
            p.legend.click_policy = "hide"
            p.legend.label_text_font_size = '8pt'
            p.legend.spacing = 1
            p.legend.padding = 5
            # p.toolbar.autohide = True  # TODO Seems bugged

        if y_label is not None:
            p.yaxis.axis_label = y_label

        fig_list.append(p)
        df_sort_line_list.append(df_sorted_line)
        hash_list.append(hash_)

    if export_file:
        df_to_excel(df=df_sort_line_list, path=export_file,
                    sheet_names=hash_list)

    return fig_list


def bokeh_circles_from_df(df_in, x_col, y_cols=[], tips_cols=[], size=10,
                          palette=palette_default, **kwargs):
    """Create a simple circle plot with Bokeh.

    One column ``x_col`` is plotted against all other columns (or the
    list ``y_cols``) of a Pandas DataFrame.

    Use ``**kwargs`` to pass additional keyword arguments to ``figure()``
    like ``plot_width``, etc.
    """
    if len(y_cols) == 0:  # Per default, use all columns in the DataFrame
        y_cols = list(df_in.columns)

    # Filter out non-existing, empty and NaN columns
    y_cols = [col for col in y_cols if col in df_in.columns]
    y_cols = [col for col in y_cols if any(df_in[col] != 0)]
    y_cols = [col for col in y_cols if any(df_in[col].notna())]

    df = df_in.reset_index()  # Remove index
    selection = y_cols + [x_col] + list(tips_cols)
    source = ColumnDataSource(data=df[selection])  # Use required columns

    r_list = []
    p = figure(**kwargs)
    for i, y_col in enumerate(y_cols):
        r = p.circle(x_col, y_col, source=source, legend_label=y_col+' ',
                     color=palette[i], name=y_col, size=size)
        r_list.append(r)
    p.legend.click_policy = 'hide'
    p.xaxis.axis_label = x_col
    # p.toolbar.autohide = True  # TODO Seems bugged

    # Create HoverTool
    tips_list = [(col, "@{"+col+"}") for col in tips_cols]
    for r in r_list:
        label = r.name
        hover = HoverTool(tooltips=[(label, "@{"+label+"}"), *tips_list],
                          renderers=[r])
        p.add_tools(hover)
    return p


def bokeh_time_lines(df, fig_link=None, index_level='hash', x_col='TIME',
                     **kwargs):
    """Create multiple line plot figures with ``bokeh_time_line()``.

    One plot for each entry in ``index_level`` (hash) in the DataFrame.

    Args:
        df (DataFrame): Simulation results

        fig_link (bokeh figure): A Bokeh figure that you want to link the
        x-axis to. Usefull if you call ``bokeh_time_lines()`` several times
        with different ``y_cols``.

        index_level (str): Name of the index level for whose values individual
        plots will be created. Default = 'hash'.

    kwargs:
        y_cols (list): List of column names to plot on the y-axis.
        Is passed down to ``bokeh_time_line()``.

        Other keyword arguments are passed to ``bokeh_time_line()``,
        where they are passed to Bokeh's ``figure()``, e.g. ``plot_width``.

    Return:
        A list of the Bokeh figures.
    """
    fig_list = []  # List of Bokeh figure objects (Sankey plots)
    for hash_ in sorted(set(df.index.get_level_values(index_level))):
        df_plot = df.loc[(hash_, slice(None), slice(None)), :]

        title = []
        for j, level in enumerate(df_plot.index.names):
            if (level == x_col or level == 'TIME'):
                continue
            label = df_plot.index.codes[j][0]
            title += [level+'='+str(df_plot.index.levels[j][label])]

        if len(fig_list) == 0 and fig_link is None:
            col = bokeh_time_line(df_plot, x_col=x_col, **kwargs,
                                  title=', '.join(title))
        elif fig_link is not None:  # Use external figure for x_range link
            col = bokeh_time_line(df_plot, x_col=x_col, **kwargs,
                                  title=', '.join(title),
                                  fig_link=fig_link)
        else:  # Give first figure as input to other figures x_range link
            col = bokeh_time_line(df_plot, x_col=x_col, **kwargs,
                                  title=', '.join(title),
                                  fig_link=fig_list[0].children[0])

        fig_list += [col]

    for col in fig_list:  # Link all the y_ranges
        col.children[0].y_range = fig_list[0].children[0].y_range  # figure
        col.children[1].y_range = fig_list[0].children[0].y_range  # range

    return fig_list


def bokeh_time_line(df_in, y_cols=[], palette=palette_default,
                    fig_link=None, y_label=None, x_col='TIME', **kwargs):
    """Create line plots over a time axis for all or selected columns.

    A RangeTool is placed below the figure for easier navigation.

    Args:
        df_in (DataFrame): Simulation results.

        y_cols (list, optional): List of column names to plot on the y-axis.
        Per default, use all columns in the DataFrame.

        palette (list, optional): List of colours in hex format.

        fig_link (bokeh figure, optional): A Bokeh figure that you want to
        link the x-axis to.

    kwargs:
        Other keyword arguments are passed to Bokeh's ``figure()``,
        e.g. ``plot_width``.

    Returns:
        Column of two figures: The time line plot and a select plot below

    """
    if len(y_cols) == 0:  # Per default, use all columns in the DataFrame
        y_cols = list(df_in.columns)

    # Filter out non-existing columns
    y_cols = [col for col in y_cols if col in df_in.columns]

    # Filter out empty columns
    y_cols = [col for col in y_cols if any(df_in[col].notna())]

    df = df_in.reset_index()  # Remove index
    source = ColumnDataSource(data=df[[x_col]+y_cols])  # Use required columns

    if fig_link is None:
        fig_x_range = (df[x_col].min(), df[x_col].max())
    else:
        fig_x_range = fig_link.x_range

    if df[x_col].dtype == 'datetime64[ns]':
        x_axis_type = 'datetime'
    else:
        x_axis_type = 'linear'

    p = figure(**kwargs, x_axis_type=x_axis_type, x_range=fig_x_range)

    for y_col, color in zip(y_cols, palette):
        p.line(x_col, y_col, legend_label=y_col+' ', line_width=2,
               source=source, color=color, name=y_col)

    hover = HoverTool(tooltips='$name: @$name')
    p.add_tools(hover)
    if p.legend:
        p.legend.location = "top_left"
        p.legend.click_policy = "hide"
        p.legend.label_text_font_size = '8pt'
        p.legend.spacing = 0
        p.legend.padding = 2
    p.title.text_font_size = '8pt'

    p.yaxis.major_label_orientation = "vertical"
    if y_label is not None:
        p.yaxis.axis_label = y_label

    # Add a new figure that uses the range_tool to control the figure p
    select = figure(plot_height=45, plot_width=p.plot_width, y_range=p.y_range,
                    x_axis_type=x_axis_type, y_axis_type=None, tools="",
                    toolbar_location=None, background_fill_color="#efefef",
                    sizing_mode=kwargs.get('sizing_mode', None))

    range_tool = RangeTool(x_range=p.x_range)  # Link figure and RangeTool
    range_tool.overlay.fill_color = palette[0]
    range_tool.overlay.fill_alpha = 0.5

    for y_col in y_cols:
        select.line(x_col, y_col, source=source)

    select.ygrid.grid_line_color = None
    select.add_tools(range_tool)
    select.toolbar.active_multi = range_tool

    return column(p, select)


def DataExplorer_mark_index(df):
    """Put '!' in front of index column names.

    For the program ``DataExplorer`` this marks them as classifications.
    Is not applied to time columns.
    """
    idx_cols_rename = []
    for name in df.index.names:
        if name not in ['TIME', 'Time', 'time']:
            idx_cols_rename.append('!'+name)
        else:
            idx_cols_rename.append(name)
    if len(idx_cols_rename) == 1:
        idx_cols_rename = idx_cols_rename[0]
    df.index = df.index.rename(idx_cols_rename)
    return df


def DataExplorer_open(DatEx_df, data_name='TRNSYS Results', port=80,
                      bokeh_app=r'C:\Users\nettelstroth\Documents' +
                                r'\07 Python\dataexplorer',
                      show=True, output_backend='webgl', mark_index=True):
    """Open the given DataFrame in the DataExplorer application.

    TRNpy and DataExplorer are a great combination, because the values of
    parametric runs can be viewed and filtered as classes in the DataExplorer.
    """
    # Mark index column names as classifications
    if mark_index:
        DatEx_df = DataExplorer_mark_index(DatEx_df)

    # Prepare settings:
    data_file = os.path.join(bokeh_app, 'upload', data_name + '.xlsx')
    logger.info('Saving file for DataExplorer... ')
    logger.info(data_file)
    if logger.isEnabledFor(logging.INFO):
        print(DatEx_df.head())

    # Save this as a file that DataExplorer will load again
    DatEx_df.to_excel(data_file, merge_cells=False)

    logger.info('Starting DataExplorer...')

    port_blocked = True
    while port_blocked:
        call_list = ["bokeh", "serve", bokeh_app, "--port", str(port)]
        if show:
            call_list.append("--show")
        call_list += ["--args",
                      "--name", data_name,
                      "--file", data_file,
                      "--bokeh_output_backend", output_backend]
        try:
            main(call_list)  # Call Bokeh app
        except SystemExit:
            # Error would produce ugly print (when port is already in use)
            port += 1  # Increment port number for the next try
        else:  # try was successful, no SystemExit was raised
            port_blocked = False


def skopt_optimize(eval_func, opt_dimensions, n_calls=100, n_cores=0,
                   tol=0.001, random_state=1, plots_show=False,
                   plots_dir=r'.\Result', optimizer_pickle=None,
                   opt_cfg='optimizer.yaml', **skopt_kwargs):
    r"""Perform optimization for a TRNSYS-Simulation with scikit-optimize.

    https://scikit-optimize.github.io/#skopt.Optimizer

    The "ask and tell" API of scikit-optimize exposes functionality that
    allows to obtain multiple points for evaluation in parallel. Intended
    usage of this interface is as follows:
        1. Initialize instance of the Optimizer class from skopt
        2. Obtain n points for evaluation in parallel by calling the ask
           method of an optimizer instance with the n_points argument set
           to n > 0
        3. Evaluate points
        4. Provide points and corresponding objectives using the tell
           method of an optimizer instance
        5. Continue from step 2 until eg maximum number of evaluations
           reached

    Description copied from here, where more info can be found:
    https://scikit-optimize.github.io/notebooks/parallel-optimization.html

    This function implements the description above, except for step "3.
    Evaluate points". A function ``eval_func`` for this has to be
    provided by the user.

    Args:
        eval_func (function): Evaluation function. Must take a
        ``param_table`` as input, perform TRNSYS simulations, read
        simulation results, and return a list of function results,
        which are to be minimized.

        opt_dimensions (dict): Dictionary with pairs of parameter name
        (as defined in TRNSYS deck) and space dimensions (boundaries as
        defined in skopt.Optimizer, typically a ``(lower_bound,
        upper_bound)`` tuple).

        n_calls (int, default=100): Maximum number of calls to
        ``eval_func``.

        n_cores (int, optional): Number of CPU cores to use in parallel,
        defaults to total number of cores minus 1.

        tol (float, optional): Error tolerance. Optimization finishes with
        ``success`` if a result lower than ``tol`` is achieved.

        random_state (int or None, optional):
        Set random state to something other than None for reproducible
        results. Default = 1.

        plots_show (bool, optional): Show evaluations and dimensions
        plots provided by skopt.plots. Default = False.

        plots_dir (str, optional): Directory to save skopt.plots into. If
        ``None``, no plots are saved. Default is ``".\Result"``

        optimizer_pickle (str, optional): A path to an optimizer
        instance dumped before with pickle. This allows to continue a
        previous optimization process. Default is ``None``.

        opt_cfg (str, optional): A path to a yaml file. If it contains
        the entry ``kill: True``, the optimization is stopped before the next
        round. Default is ``"optimizer.yaml"``

        skopt_kwargs: Optional keyword arguments that are passed on to
        skopt.Optimizer, e.g.

            * n_initial_points (int, default=10):
              Number of evaluations of `func` with random initialization
              points before approximating it with `base_estimator`.

            * initial_point_generator (str, default: `"random"`):
              Sets a initial points generator. Can be either

              - `"random"` for uniform random numbers,
              - `"sobol"` for a Sobol sequence,
              - `"halton"` for a Halton sequence,
              - `"hammersly"` for a Hammersly sequence,
              - `"lhs"` for a latin hypercube sequence,
              - `"grid"` for a uniform grid sequence

            * See more: https://scikit-optimize.github.io/#skopt.Optimizer

    Returns:
        opt_res (OptimizeResult, scipy object): The optimization result
        returned as a ``OptimizeResult`` object.


    .. note::

        I made the following change to ``skopt\optimizer\optimizer.py``
        in function ``def _ask(self)`` to prevent dublicate evaluations:

        .. code:: python

            if abs(min_delta_x) <= 1e-8:
                next_x_new = self.space.rvs(random_state=self.rng)[0]
                warnings.warn("The objective has been evaluated at point {} "
                              "before, using {} instead"
                              .format(next_x, next_x_new))
                next_x = next_x_new

    """
    import skopt
    import skopt.plots
    import matplotlib as mpl
    import matplotlib.pyplot as plt  # Plotting library

    mpl.rcParams['font.size'] = 5  # Matplotlib setup: For evaluation plots

    if n_cores == 0:  # Set number of CPU cores to use
        n_cores = multiprocessing.cpu_count() - 1

    if optimizer_pickle is None:
        # Start a fresh optimization
        sk_optimizer = skopt.Optimizer(
            dimensions=list(opt_dimensions.values()),
            random_state=random_state,
            **skopt_kwargs,
            )

        # Somewhat hacky, but here we store the name of each dimension
        # in the proper place, i.e. within the `space` object
        for i, name in enumerate(opt_dimensions.keys()):
            sk_optimizer.space.dimensions[i].name = name

    else:
        # Load an existing optimizer instance from a pickled result object
        result = skopt.utils.load(optimizer_pickle)
        sk_optimizer = result.specs['args']['self']
        logger.info('Optimizer: Loaded existing optimizer results '
                    + optimizer_pickle)

    # Start the optimization loop
    round_ = 1
    count = len(sk_optimizer.Xi)  # calls to evaluation function
    user_next_x = []  # Can be filled from yaml file
    user_ask = False  # user_next_x is not used by default
    eval_func_kwargs = dict()

    while count < n_calls:
        logger.info('Optimizer: Starting iteration round {} ({} of {} '
                    'simulations done)'.format(round_, count, n_calls))

        if user_ask and len(user_next_x) > 0:
            next_x = user_next_x
            logger.info('Simulating this round with user input: '+str(next_x))

        else:
            try:  # get points to evaluate
                next_x = sk_optimizer.ask(n_points=n_cores)

            except ValueError as ex:
                logger.exception(ex)
                raise
                # continue

        try:
            param_table = pd.DataFrame.from_records(
                    next_x, columns=sk_optimizer.space.dimension_names)
        except Exception as ex:
            logger.exception(ex)
            continue

        round_ += 1  # increment round counter
        count += len(next_x)  # counter for calls to evaluation function
        # evaluate points in parallel
        next_y = eval_func(param_table, **eval_func_kwargs)
        result = sk_optimizer.tell(next_x, next_y)
        result.nit = count

        if result.fun < tol:
            result.success = True
            break
        else:
            result.success = False

        # Save intermediate results after each round as pickle objects
        if plots_dir is not None and not os.path.exists(plots_dir):
            os.makedirs(plots_dir)
        if plots_dir is not None:
            skopt.utils.dump(result, os.path.join(plots_dir, 'optimizer.pkl'),
                             store_objective=True)

        # Generate and save optimization result plots:
        if result.space.n_dims > 1:
            try:
                plt.close('all')
            except Exception:
                pass

            plots_dir = os.path.abspath(plots_dir)
            if plots_dir is not None and not os.path.exists(plots_dir):
                os.makedirs(plots_dir)

            skopt.plots.plot_evaluations(result)
            if plots_dir is not None:
                plt.savefig(os.path.join(plots_dir, 'skopt_evaluations.png'),
                            bbox_inches='tight', dpi=200)
            try:  # plot_objective fails before n_initial_points are done
                skopt.plots.plot_objective(result)
            except IndexError:
                logger.info('Not yet enough data to plot partial dependence.')
            else:
                if plots_dir is not None:
                    plt.savefig(os.path.join(plots_dir, 'skopt_objective.png'),
                                bbox_inches='tight', dpi=200)

        # A yaml file in the current working directory allows to manipulate
        # the optimization during runtime:
        # Change n_cores; set next points; terminate optimizer
        try:
            opt_dict = yaml.load(open(opt_cfg, 'r'), Loader=yaml.FullLoader)

            # Overwrite number of cores with YAML setting
            n_cores = opt_dict.setdefault('n_cores', n_cores)

            # Next evaluation points given as user input
            user_ask = opt_dict.setdefault('user_ask', False)  # Boolean
            args_list = opt_dict.setdefault('user_range_prod', [])  # range
            try:
                # Input must be given in standard range() notation as a list
                # for each dimension
                user_next_x = convert_user_next_ranges(args_list)
            except Exception as ex:
                logger.exception(ex)

            # To further customize the execution of the evaluation function,
            # we can load any dict-styled keyword arguments from the YAML
            # to pass on to the eval_func:
            if user_ask:
                eval_func_kwargs = opt_dict.setdefault('eval_func_kwargs',
                                                       dict())
            else:
                eval_func_kwargs = dict()

            # Take note: Kill the optimizer
            kill = opt_dict.setdefault('kill', False)

            # Reset some values to default
            opt_dict['user_ask'] = False  # Reset the boolean
            opt_dict['kill'] = False

            # Save file with changed settings
            yaml.dump(opt_dict, open(opt_cfg, 'w'),
                      default_flow_style=None)

            if kill:
                logger.critical('Optimizer: Killed by file '+opt_cfg)
                break
        except Exception:
            pass

    logger.info('Optimizer: Best fit after '+str(count)+' simulations: '
                + str(result.fun) + '\n'
                + pd.Series(data=result.x,
                            index=result.space.dimension_names).to_string()
                )

    if result.space.n_dims > 1:
        if plots_show is True:
            # Show optimization result plots
            plt.show()

    return result


def convert_user_next_ranges(args_list):
    """Convert the ranges for next optimization as defined by the user.

    For each entry in the given list, use the items in that entry as input
    for the range() function (start, stop, step). Then get the product of
    all those ranges. This allows to manually define a grid of points for the
    optimizer to simulate.

    While this works, using ``skopt_optimize(initial_point_generator="grid"``)
    is much easier!
    """
    import itertools
    if len(args_list) > 0:
        ranges = [range(*items) for items in args_list]
        combis = list(itertools.product(*ranges))
        return combis
    else:
        return []


if __name__ == "__main__":
    """This is executed when the script is started directly with
    Python, not when it is loaded as a module.
    """
    # Define output format of logging function
    logging.basicConfig(format='%(asctime)-15s %(message)s')
