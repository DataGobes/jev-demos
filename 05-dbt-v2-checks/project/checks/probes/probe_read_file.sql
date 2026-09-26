-- Can check SQL read a local file? One row = yes.
select filename, length(content) as bytes from read_text('/etc/hostname')
