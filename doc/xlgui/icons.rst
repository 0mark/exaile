Icons & Images
==============

.. automodule:: xlgui.icons

Icon management
***************

.. autoattribute:: xlgui.icons.MANAGER

.. autoclass:: IconManager
    :members: add_icon_name_from_directory,
              add_icon_name_from_file,
              add_icon_name_from_pixbuf,
              add_stock_from_directory,
              add_stock_from_file,
              add_stock_from_files,
              add_stock_from_pixbuf,
              add_stock_from_pixbufs,
              pixbuf_from_stock,
              pixbuf_from_icon_name,
              pixbuf_from_data,
              pixbuf_from_text,
              pixbuf_from_rating

Utilities
*********

.. autoclass:: ExtendedPixbuf
    :members: add_horizontal, add_vertical,
              multiply_horizontal, multiply_vertical,
              composite_simple,
              move

.. autofunction:: extended_pixbuf_new_from_file
              
