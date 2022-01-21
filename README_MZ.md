# TRAINED MODEL FILES
Uploaded the files of the trained model on the COCO 2014 Dataset in the folder /model with the woman.jpg style image.
You can have a glimpse of the results in the /MZ_test_output folder.

# CHANGES FOR WINDOWS
If you want to retrain the model on another style image, change all the instances of

```python
os.path.join(...)
```

with
```python
os.path.normpath(os.path.join(...))
```
